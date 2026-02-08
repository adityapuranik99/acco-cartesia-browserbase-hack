from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

from brain import Brain
from browser_controller import BrowserController
from domain_verifier import DomainVerifier
from models import ActionPlan, AgentState, ExecutionResult, RiskLevel, ServerEvent


SUBMIT_KEYWORDS = {
    "submit",
    "place order",
    "pay now",
    "confirm payment",
    "complete payment",
    "finish payment",
}


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
        safe_payment_domains: list[str] | None = None,
        exa_api_key: str = "",
        enable_exa_verification: bool = False,
    ) -> None:
        self.state = AgentState()
        self.pending_plan: ActionPlan | None = None
        self.safe_payment_domains = set((safe_payment_domains or []))
        self.max_steps_per_turn = 4
        self.domain_verifier = DomainVerifier(api_key=exa_api_key, enabled=enable_exa_verification)

        self.brain = Brain(
            anthropic_api_key=anthropic_api_key,
            timeout_sec=claude_timeout_sec,
            enabled=enable_claude,
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
        normalized = transcript.strip().lower()

        if self.state.pending_confirmation:
            expected = (self.state.pending_confirmation_phrase or "").lower()
            if normalized == expected:
                self.state.pending_confirmation = False
                self.state.pending_confirmation_phrase = None
                yield ServerEvent(type="agent_response", text="Confirmation received. Continuing safely.")
                if self.pending_plan is not None:
                    pending = self.pending_plan
                    self.pending_plan = None
                    async for event in self._execute_plan(pending, self.state.current_goal or transcript, step_index=0):
                        yield event
                else:
                    yield ServerEvent(type="risk_update", risk_level="SAFE")
            else:
                yield ServerEvent(
                    type="agent_response",
                    text=f"Please say exactly: '{self.state.pending_confirmation_phrase}'.",
                )
            return

        self.state.current_goal = transcript
        self.state.action_history = []

        for step in range(1, self.max_steps_per_turn + 1):
            plan = await self.brain.plan_action(transcript=self.state.current_goal, state=self.state)
            plan = self._normalize_plan(plan)
            signature = self._plan_signature(plan)

            if plan.action_type == "noop":
                if step == 1:
                    yield ServerEvent(type="agent_response", text="How would you like me to proceed?")
                return

            if signature and signature in self.state.action_history[-2:]:
                yield ServerEvent(
                    type="agent_response",
                    text="I appear to be repeating steps. Please clarify the next action.",
                )
                return

            gated = await self._enforce_safety_gate(plan, self.state.current_goal)
            if gated is not None:
                if self.state.last_risk_level in {"HIGH_RISK", "DANGER"}:
                    yield ServerEvent(type="risk_update", risk_level=self.state.last_risk_level)
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

        if plan.requires_confirmation or is_submit_action or (payment_intent and plan.action_type in {"navigate", "act", "extract"}):
            phrase, readback = await self._build_payment_confirmation()
            if not phrase:
                phrase = plan.confirmation_phrase or "yes, proceed safely"

            self.pending_plan = plan.model_copy(update={"requires_confirmation": False, "confirmation_phrase": None})
            self.state.pending_confirmation = True
            self.state.pending_confirmation_phrase = phrase
            self.state.last_risk_level = "HIGH_RISK"

            prefix = "Safety check required before this high-risk step."
            if readback:
                prefix = f"{prefix} {readback}"

            return ServerEvent(
                type="agent_response",
                text=f"{prefix} Please say exactly: '{phrase}'.",
            )

        return None

    async def _execute_plan(self, plan: ActionPlan, transcript: str, step_index: int) -> AsyncIterator[ServerEvent]:
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
            result = await self.browser.navigate(str(plan.url))
        elif plan.action_type == "act" and plan.instruction:
            result = await self.browser.act(plan.instruction)
        elif plan.action_type == "extract" and plan.instruction:
            result = await self.browser.extract(plan.instruction)
        elif plan.action_type == "stop":
            yield ServerEvent(type="agent_response", text="Stopping now.")
            return
        else:
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

        quick_assessment = self.brain.analyze_page_risk_fast(transcript=transcript, snapshot=snapshot)
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
        assessment = await deep_assessment_task
        domain_verification = await domain_verification_task
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
            yield ServerEvent(type="agent_response", text=result.message)
            return

        voice_message = assessment.voice_message or self._voice_message(assessment.risk_level)
        yield ServerEvent(type="agent_response", text=f"{voice_message} {result.message}")

        if result.extracted_data is not None:
            yield ServerEvent(
                type="status",
                text="Extracted page data.",
                metadata={"extracted_data": result.extracted_data},
            )

        if assessment.recommended_action == "block":
            self.state.last_risk_level = "DANGER"
            yield ServerEvent(type="agent_response", text="I am blocking further automated actions on this page.")
            return

        if assessment.requires_confirmation and not self.state.pending_confirmation:
            phrase = assessment.confirmation_phrase or "yes, proceed safely"
            self.state.pending_confirmation = True
            self.state.pending_confirmation_phrase = phrase
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
        phrase = f"yes, pay {amount_readback} to {payee_readback}"
        readback = f"I read the amount as {amount_readback} to {payee_readback}."
        return phrase, readback

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
        if risk_level == "DANGER":
            return "Hold on. This page appears risky or deceptive."
        if risk_level == "HIGH_RISK":
            return "I found a high-risk step and will proceed carefully."
        if risk_level == "CAUTION":
            return "This page requests sensitive information."
        return "Navigation looks safe so far."
