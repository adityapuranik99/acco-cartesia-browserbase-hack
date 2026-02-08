from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

from brain import Brain, GMAIL_FIND_AND_OPEN_LINK_MARKER, PGE_CLICK_SIGN_IN_MARKER, PGE_FILL_CREDENTIALS_MARKER
from browser_controller import BrowserController
from domain_verifier import DomainVerifier
from models import ActionPlan, AgentState, ExecutionResult, RiskLevel, ServerEvent, VoiceState


SUBMIT_KEYWORDS = {
    "submit",
    "place order",
    "pay now",
    "confirm payment",
    "complete payment",
    "finish payment",
}
PAYMENT_CONFIRMATION_PHRASE = "yes I have checked, please proceed"


class AccessibilityCopilot:
    def __init__(
        self,
        anthropic_api_key: str,
        browserbase_api_key: str,
        browserbase_project_id: str,
        model_api_key: str = "",
        stagehand_model_name: str = "anthropic/claude-sonnet-4-5",
        stagehand_timeout_sec: float = 12.0,
        enable_stagehand: bool = False,
        claude_timeout_sec: float = 10.0,
        enable_claude: bool = False,
        enable_fast_risk_model: bool = True,
        fast_risk_model_name: str = "claude-3-5-haiku-20241022",
        fast_risk_timeout_sec: float = 2.2,
        safe_payment_domains: list[str] | None = None,
        exa_api_key: str = "",
        enable_exa_verification: bool = False,
        demo_gmail_email: str = "",
        demo_gmail_password: str = "",
        demo_pge_email: str = "",
        demo_pge_password: str = "",
    ) -> None:
        self.state = AgentState()
        self.pending_plan: ActionPlan | None = None
        self.safe_payment_domains = set((safe_payment_domains or []))
        self.max_steps_per_turn = 4
        self.progress_ping_sec = 2.5
        self.domain_verifier = DomainVerifier(api_key=exa_api_key, enabled=enable_exa_verification)

        self.brain = Brain(
            anthropic_api_key=anthropic_api_key,
            timeout_sec=claude_timeout_sec,
            enabled=enable_claude,
            enable_fast_risk_model=enable_fast_risk_model,
            fast_risk_model_name=fast_risk_model_name,
            fast_risk_timeout_sec=fast_risk_timeout_sec,
            demo_gmail_email=demo_gmail_email,
            demo_gmail_password=demo_gmail_password,
            demo_pge_email=demo_pge_email,
            demo_pge_password=demo_pge_password,
        )
        self.browser = BrowserController(
            browserbase_api_key=browserbase_api_key,
            browserbase_project_id=browserbase_project_id,
            model_api_key=model_api_key,
            stagehand_model_name=stagehand_model_name,
            stagehand_timeout_sec=stagehand_timeout_sec,
            enable_stagehand=enable_stagehand,
        )

    async def start(self) -> None:
        await self.browser.start()

    async def shutdown(self) -> None:
        await self.browser.shutdown()

    def runtime_info(self) -> dict[str, str]:
        info: dict[str, str] = {"browser_mode": self.browser.mode}
        if self.browser.session_id:
            info["session_id"] = self.browser.session_id
        if self.browser.live_view_url:
            info["live_view_url"] = self.browser.live_view_url
        return info

    async def handle_transcript(self, transcript: str) -> AsyncIterator[ServerEvent]:
        yield self._voice_state("LISTENING", "I heard you.")
        normalized = transcript.strip().lower()

        if self.state.pending_confirmation:
            # Simple yes/no check
            if any(word in normalized for word in ["no", "stop", "cancel", "don't", "dont"]):
                self.state.pending_confirmation = False
                self.state.pending_confirmation_phrase = None
                self.pending_plan = None
                yield ServerEvent(type="agent_response", text="Okay, stopped. What else can I help with?")
                yield ServerEvent(type="risk_update", risk_level="SAFE")
                return

            if any(word in normalized for word in ["yes", "okay", "ok", "proceed", "continue", "go ahead"]):
                self.state.pending_confirmation = False
                self.state.pending_confirmation_phrase = None
                yield ServerEvent(type="agent_response", text="Got it! Continuing...")
                if self.pending_plan is not None:
                    pending = self.pending_plan
                    self.pending_plan = None
                    async for event in self._execute_plan(pending, self.state.current_goal or transcript, step_index=0):
                        yield event
                return

            # Didn't understand
            yield ServerEvent(type="agent_response", text="Sorry, I didn't catch that. Say 'yes' or 'no'.")
            return

        yield self._voice_state("ACK", "Understood. Starting now.")
        self.state.current_goal = transcript
        self.state.action_history = []

        for step in range(1, self.max_steps_per_turn + 1):
            plan = await self.brain.plan_action(transcript=self.state.current_goal, state=self.state)
            plan = self._normalize_plan(plan)
            signature = self._plan_signature(plan)

            if plan.action_type == "noop":
                if step == 1:
                    yield self._voice_state("RESULT")
                    yield ServerEvent(type="agent_response", text="How would you like me to proceed?")
                return

            if signature and signature in self.state.action_history[-2:]:
                yield self._voice_state("RESULT")
                yield ServerEvent(
                    type="agent_response",
                    text="I appear to be repeating steps. Please clarify the next action.",
                )
                return

            gated = await self._enforce_safety_gate(plan, self.state.current_goal)
            if gated is not None:
                if self.state.last_risk_level in {"High Risk", "DANGER"}:
                    yield ServerEvent(type="risk_update", risk_level=self.state.last_risk_level)
                yield self._voice_state("SAFETY_CHECK")
                yield gated
                return

            async for event in self._execute_plan(plan, self.state.current_goal, step_index=step):
                yield event

            if signature:
                self.state.action_history.append(signature)

            if self.state.pending_confirmation:
                return
            if plan.action_type in {"stop", "extract"}:
                return
            if self.state.last_risk_level == "DANGER":
                yield self._voice_state("RESULT")
                yield ServerEvent(
                    type="agent_response",
                    text="I am stopping here because the current page appears dangerous.",
                )
                return

    async def _enforce_safety_gate(self, plan: ActionPlan, transcript: str) -> ServerEvent | None:
        lower_transcript = transcript.lower()
        payment_intent = any(token in lower_transcript for token in ["pay", "payment", "bill", "card", "checkout"])

        if payment_intent and plan.action_type == "navigate" and plan.url is not None and self.safe_payment_domains:
            host = (urlparse(str(plan.url)).hostname or "").lower()
            if not any(host == d or host.endswith(f".{d}") for d in self.safe_payment_domains):
                self.state.last_risk_level = "DANGER"
                return ServerEvent(
                    type="agent_response",
                    text=(
                        f"I blocked navigation to {host} because it is not in the approved payment domain list. "
                        "Please specify a trusted utility domain."
                    ),
                )

        instruction = (plan.instruction or "").lower()
        is_submit_action = plan.action_type == "act" and any(token in instruction for token in SUBMIT_KEYWORDS)

        if plan.requires_confirmation or is_submit_action:
            phrase, readback = await self._build_payment_confirmation()
            if not phrase:
                phrase = plan.confirmation_phrase or PAYMENT_CONFIRMATION_PHRASE

            self.pending_plan = plan.model_copy(update={"requires_confirmation": False, "confirmation_phrase": None})
            self.state.pending_confirmation = True
            self.state.pending_confirmation_phrase = phrase
            self.state.last_risk_level = "High Risk"

            prefix = "Safety check required before this high-risk step."
            if readback:
                prefix = f"{prefix} {readback}"

            return ServerEvent(
                type="agent_response",
                text=f"{prefix} Please say exactly: '{phrase}'.",
            )

        return None

    async def _execute_plan(self, plan: ActionPlan, transcript: str, step_index: int) -> AsyncIterator[ServerEvent]:
        yield self._voice_state("WORKING")
        status_meta = self.runtime_info()
        status_meta["step"] = str(step_index)
        yield ServerEvent(
            type="status",
            text=f"Action: {plan.action_type} ({plan.reason})",
            metadata=status_meta,
        )
        yield ServerEvent(type="agent_response", text="Working on that now.")

        result = ExecutionResult(success=True, message="No operation.", current_url=self.state.last_url)
        if plan.action_type == "navigate" and plan.url is not None:
            action_task = asyncio.create_task(self.browser.navigate(str(plan.url)))
            wait_tick = 0
            while True:
                try:
                    result = await asyncio.wait_for(asyncio.shield(action_task), timeout=self.progress_ping_sec)
                    break
                except asyncio.TimeoutError:
                    wait_tick += 1
                    yield ServerEvent(
                        type="status",
                        text="Still loading the page.",
                        metadata={"step": str(step_index), "wait_tick": str(wait_tick)},
                    )
                    if wait_tick == 1 or wait_tick % 2 == 0:
                        yield ServerEvent(type="agent_response", text="Still working on the page load.")
        elif plan.action_type == "act" and plan.instruction:
            if plan.instruction == GMAIL_FIND_AND_OPEN_LINK_MARKER:
                yield ServerEvent(
                    type="status",
                    text="Analyzing email content for the relevant billing link.",
                    metadata={"step": str(step_index)},
                )
                snapshot = await self.browser.capture_page_state()
                if snapshot.current_url:
                    self.state.last_url = snapshot.current_url
                    yield ServerEvent(type="browser_update", url=snapshot.current_url)

                link_info = await self.brain.infer_email_payment_link(snapshot)
                link_url = (link_info.get("url") or "").strip()

                if link_url:
                    result = await self.browser.navigate(link_url)
                    if result.success:
                        result.message = "Opened the billing link from the email."
                    else:
                        result.message = f"I found a link but couldn't open it automatically: {link_url}. {result.message}"
                else:
                    open_email_result = await self.browser.act(
                        "From the inbox list, open an email whose subject or sender mentions PG&E, bill, payment, due, or statement. "
                        "If none is visible, open the topmost email row."
                    )
                    if not open_email_result.success:
                        result = open_email_result
                    else:
                        refreshed = await self.browser.capture_page_state()
                        if refreshed.current_url:
                            self.state.last_url = refreshed.current_url
                            yield ServerEvent(type="browser_update", url=refreshed.current_url)
                        followup_link = await self.brain.infer_email_payment_link(refreshed)
                        followup_url = (followup_link.get("url") or "").strip()
                        if followup_url:
                            result = await self.browser.navigate(followup_url)
                            if result.success:
                                result.message = "Opened the billing link from the selected email."
                            else:
                                result.message = (
                                    f"I found a link but couldn't open it automatically: {followup_url}. {result.message}"
                                )
                        else:
                            result = ExecutionResult(
                                success=False,
                                message="I opened the email but could not detect a reliable billing link yet.",
                                current_url=self.state.last_url,
                            )
            elif plan.instruction == PGE_CLICK_SIGN_IN_MARKER:
                pge_attempts = [
                    "Close or accept any cookie/privacy banner that blocks page interactions.",
                    "Click the 'Sign In' button or link for account access.",
                    "If not found, click 'Log In' for account access.",
                    "If still not found, click the account/profile/menu icon in the header, then click 'Sign In'.",
                ]
                last_fail: ExecutionResult | None = None
                result = ExecutionResult(success=False, message="Could not find the PG&E sign-in button.")
                for idx, attempt in enumerate(pge_attempts):
                    attempt_result = await self.browser.act(attempt)
                    if idx == 0:
                        # Banner handling is best-effort; continue regardless.
                        continue
                    if attempt_result.success:
                        result = attempt_result
                        result.message = "Clicked the PG&E sign-in action."
                        break
                    last_fail = attempt_result
                if not result.success and last_fail is not None:
                    result = last_fail
            elif plan.instruction.startswith(f"{PGE_FILL_CREDENTIALS_MARKER}|"):
                parts = plan.instruction.split("|", 2)
                if len(parts) != 3:
                    result = ExecutionResult(
                        success=False,
                        message="I could not parse the credentials payload for PG&E fill.",
                        current_url=self.state.last_url,
                    )
                else:
                    email_value, password_value = parts[1], parts[2]
                    direct_fill_result = await self.browser.fill_login_credentials(email=email_value, password=password_value)
                    if direct_fill_result.success:
                        result = direct_fill_result
                    else:
                        result = direct_fill_result
                    pre_steps = [
                        "If sign-in fields are not visible, click the main 'Sign In' button first.",
                        f"Fill in the email or username field with: {email_value}",
                    ]
                    if not result.success:
                        for step in pre_steps:
                            pre = await self.browser.act(step)
                            if not pre.success:
                                result = pre
                                break
                        else:
                            password_attempts = [
                                f"Fill in the 'Password' field with: {password_value}",
                                f"Click the password input box and type: {password_value}",
                                f"Fill in the input of type password with: {password_value}",
                                f"Focus the password field, clear any existing value, then type exactly: {password_value}",
                            ]
                            result = ExecutionResult(
                                success=False,
                                message="I could not fill the password field reliably.",
                                current_url=self.state.last_url,
                            )
                            for attempt in password_attempts:
                                attempt_result = await self.browser.act(attempt)
                                if attempt_result.success:
                                    result = attempt_result
                                    result.message = "Filled PG&E email and password fields."
                                    break
            else:
                action_task = asyncio.create_task(self.browser.act(plan.instruction))
                wait_tick = 0
                while True:
                    try:
                        result = await asyncio.wait_for(asyncio.shield(action_task), timeout=self.progress_ping_sec)
                        break
                    except asyncio.TimeoutError:
                        wait_tick += 1
                        yield ServerEvent(
                            type="status",
                            text="Still carrying out the requested action.",
                            metadata={"step": str(step_index), "wait_tick": str(wait_tick)},
                        )
                        if wait_tick == 1 or wait_tick % 2 == 0:
                            yield ServerEvent(type="agent_response", text="Still working on that action.")
        elif plan.action_type == "extract" and plan.instruction:
            action_task = asyncio.create_task(self.browser.extract(plan.instruction))
            wait_tick = 0
            while True:
                try:
                    result = await asyncio.wait_for(asyncio.shield(action_task), timeout=self.progress_ping_sec)
                    break
                except asyncio.TimeoutError:
                    wait_tick += 1
                    yield ServerEvent(
                        type="status",
                        text="Still extracting page information.",
                        metadata={"step": str(step_index), "wait_tick": str(wait_tick)},
                    )
                    if wait_tick == 1 or wait_tick % 2 == 0:
                        yield ServerEvent(type="agent_response", text="Still gathering details from this page.")
        elif plan.action_type == "stop":
            yield self._voice_state("RESULT")
            yield ServerEvent(type="agent_response", text="Stopping now.")
            return
        else:
            yield self._voice_state("RESULT")
            yield ServerEvent(type="agent_response", text="How would you like me to proceed?")
            return

        if result.current_url:
            self.state.last_url = result.current_url
            yield ServerEvent(type="browser_update", url=result.current_url)

        yield ServerEvent(type="agent_response", text="Page loaded. Running a quick safety check first.")
        snapshot = await self.browser.capture_page_state()
        if snapshot.current_url:
            self.state.last_url = snapshot.current_url
        self.state.last_page_snapshot = snapshot.model_dump(exclude={"screenshot_b64"})

        quick_assessment = await self.brain.analyze_page_risk_fast(transcript=transcript, snapshot=snapshot)
        self.state.last_risk_level = quick_assessment.risk_level
        yield ServerEvent(
            type="risk_update",
            risk_level=quick_assessment.risk_level,
            metadata={"analysis_stage": "fast", "step": str(step_index)},
        )
        yield ServerEvent(
            type="status",
            text="Fast risk pass complete. Running deeper analysis.",
            metadata={
                "risk_reasons": quick_assessment.risk_reasons,
                "recommended_action": quick_assessment.recommended_action,
                "step": str(step_index),
                "analysis_stage": "fast",
            },
        )
        yield ServerEvent(type="agent_response", text="One moment while I run a deeper safety scan.")

        deep_assessment_task = asyncio.create_task(self.brain.analyze_page_risk(transcript=transcript, snapshot=snapshot))
        domain_verification_task = asyncio.create_task(
            self._verify_domain_if_needed(plan=plan, transcript=transcript, snapshot=snapshot)
        )
        combined_task = asyncio.gather(deep_assessment_task, domain_verification_task)
        wait_tick = 0
        while True:
            try:
                assessment, domain_verification = await asyncio.wait_for(
                    asyncio.shield(combined_task),
                    timeout=self.progress_ping_sec,
                )
                break
            except asyncio.TimeoutError:
                wait_tick += 1
                yield ServerEvent(
                    type="status",
                    text="Deep analysis still running.",
                    metadata={
                        "step": str(step_index),
                        "analysis_stage": "deep",
                        "wait_tick": str(wait_tick),
                    },
                )
                if wait_tick == 1 or wait_tick % 2 == 0:
                    yield ServerEvent(type="agent_response", text="I am still checking safety signals.")

        assessment = self._apply_domain_verification_assessment(assessment, domain_verification)

        if (
            assessment.risk_level != quick_assessment.risk_level
            or assessment.recommended_action != quick_assessment.recommended_action
            or assessment.requires_confirmation != quick_assessment.requires_confirmation
        ):
            self.state.last_risk_level = assessment.risk_level
            yield ServerEvent(
                type="risk_update",
                risk_level=assessment.risk_level,
                metadata={"analysis_stage": "deep", "step": str(step_index)},
            )
            yield ServerEvent(
                type="agent_response",
                text=(
                    f"Update: deeper analysis changed risk from {quick_assessment.risk_level} "
                    f"to {assessment.risk_level}."
                ),
            )

        yield ServerEvent(
            type="status",
            text="Risk analysis updated.",
            metadata={
                "risk_reasons": assessment.risk_reasons,
                "recommended_action": assessment.recommended_action,
                "step": str(step_index),
                "analysis_stage": "deep",
                "domain_verification": domain_verification or {},
            },
        )

        if not result.success:
            yield self._voice_state("RESULT")
            yield ServerEvent(type="agent_response", text=result.message)
            return

        voice_message = assessment.voice_message or self._voice_message(assessment.risk_level)
        yield self._voice_state("RESULT")
        yield ServerEvent(type="agent_response", text=f"{voice_message} {result.message}")

        if result.extracted_data is not None:
            yield ServerEvent(
                type="status",
                text="Extracted page data.",
                metadata={"extracted_data": result.extracted_data},
            )

        if assessment.recommended_action == "block":
            self.state.last_risk_level = "DANGER"
            yield self._voice_state("SAFETY_CHECK")
            yield ServerEvent(type="agent_response", text="I am blocking further automated actions on this page.")
            return

        if assessment.requires_confirmation and not self.state.pending_confirmation:
            phrase = assessment.confirmation_phrase or PAYMENT_CONFIRMATION_PHRASE
            self.state.pending_confirmation = True
            self.state.pending_confirmation_phrase = phrase
            yield self._voice_state("SAFETY_CHECK")
            yield ServerEvent(
                type="agent_response",
                text=f"Before continuing, please say exactly: '{phrase}'.",
            )

    async def _build_payment_confirmation(self) -> tuple[str, str]:
        details = await self.browser.extract_payment_details()
        amount = (details.get("amount") or "").strip()
        payee = (details.get("payee") or "").strip()

        amount_readback = amount or "the displayed amount"
        payee_readback = payee or "the displayed payee"
        phrase = PAYMENT_CONFIRMATION_PHRASE
        readback = f"I read the amount as {amount_readback} to {payee_readback}."
        return phrase, readback

    def _voice_state(self, state: VoiceState, text: str | None = None) -> ServerEvent:
        return ServerEvent(type="voice_state", voice_state=state, text=text)

    def _plan_signature(self, plan: ActionPlan) -> str:
        url = str(plan.url) if plan.url else ""
        return f"{plan.action_type}|{url}|{plan.instruction or ''}".strip()

    def _normalize_plan(self, plan: ActionPlan) -> ActionPlan:
        if plan.action_type == "navigate" and plan.url is None:
            return ActionPlan(action_type="noop", reason="Planner returned navigate without URL.")

        if plan.action_type == "act" and not (plan.instruction or "").strip():
            return ActionPlan(action_type="noop", reason="Planner returned act without instruction.")

        if plan.action_type == "extract" and not (plan.instruction or "").strip():
            return ActionPlan(
                action_type="extract",
                reason=plan.reason or "Default page extraction.",
                instruction="Summarize what this page is about and list key actionable elements.",
            )

        return plan

    async def _verify_domain_if_needed(
        self,
        plan: ActionPlan,
        transcript: str,
        snapshot: Any,
    ) -> dict[str, object] | None:
        if not self.domain_verifier.enabled:
            return None

        service_name = self._resolve_service_name(plan, transcript, snapshot)
        if not service_name:
            return None

        current_url = snapshot.current_url or self.state.last_url
        result = await self.domain_verifier.verify_service_domain(service_name=service_name, current_url=current_url)
        if plan.service_name:
            self.state.expected_service = plan.service_name
        return result

    def _resolve_service_name(self, plan: ActionPlan, transcript: str, snapshot: Any) -> str:
        if plan.service_name and plan.service_name.strip():
            return plan.service_name.strip()

        if self.state.expected_service and self.state.expected_service.strip():
            return self.state.expected_service.strip()

        payee = getattr(snapshot, "payee_entity", None)
        if isinstance(payee, str) and payee.strip() and payee.lower() not in {"unknown", "n/a"}:
            return payee.strip()

        lower = transcript.lower()
        if "pg&e" in lower or "pge" in lower:
            return "PG&E"
        if "google" in lower:
            return "Google"
        return ""

    def _apply_domain_verification_assessment(
        self,
        assessment: Any,
        domain_verification: dict[str, object] | None,
    ) -> Any:
        if not domain_verification or not domain_verification.get("checked"):
            return assessment

        if domain_verification.get("match", False):
            return assessment

        current_domain = str(domain_verification.get("current_domain", "unknown"))
        verified_domain = str(domain_verification.get("verified_domain", "unknown"))
        service_name = str(domain_verification.get("service_name", "service"))

        reasons = list(assessment.risk_reasons)
        reasons.append(
            f"Domain mismatch detected for {service_name}: current domain {current_domain}, verified domain {verified_domain}."
        )

        return assessment.model_copy(
            update={
                "risk_level": "DANGER",
                "risk_reasons": reasons,
                "recommended_action": "block",
                "voice_message": (
                    f"Hold on. This page is on {current_domain}, but {service_name}'s official domain is "
                    f"{verified_domain}. I am blocking this action."
                ),
                "requires_confirmation": False,
                "confirmation_phrase": None,
            }
        )

    def _voice_message(self, risk_level: RiskLevel) -> str:
        """Generate natural, friendly voice messages."""
        if risk_level == "DANGER":
            return "Whoa, hold on! This page looks suspicious to me. I think it might be a scam."
        if risk_level == "High Risk":
            return "Hey, I found a payment button. Want me to click it? Just say yes or no."
        if risk_level == "CAUTION":
            return "I see a form here. What would you like me to fill in?"
        return "Page loaded! What can I help you with?"
