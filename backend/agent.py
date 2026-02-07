from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import urlparse

from brain import Brain
from browser_controller import BrowserController
from models import ActionPlan, AgentState, ExecutionResult, RiskLevel, ServerEvent


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
    ) -> None:
        self.state = AgentState()
        self.pending_plan: ActionPlan | None = None
        self.safe_payment_domains = set((safe_payment_domains or []))
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

        # Deterministic safety middleware: exact phrase required when pending.
        if self.state.pending_confirmation:
            expected = (self.state.pending_confirmation_phrase or "").lower()
            if normalized == expected:
                self.state.pending_confirmation = False
                self.state.pending_confirmation_phrase = None
                yield ServerEvent(type="agent_response", text="Confirmation received. Continuing safely.")
                if self.pending_plan is not None:
                    pending = self.pending_plan
                    self.pending_plan = None
                    async for event in self._execute_plan(pending, transcript):
                        yield event
                else:
                    yield ServerEvent(type="risk_update", risk_level="SAFE")
            else:
                yield ServerEvent(
                    type="agent_response",
                    text=f"Please say exactly: '{self.state.pending_confirmation_phrase}'.",
                )
            return

        plan = await self.brain.plan_action(transcript=transcript, state=self.state)
        gated = self._enforce_safety_gate(plan, transcript)

        if gated is not None:
            if self.state.last_risk_level in {"HIGH_RISK", "DANGER"}:
                yield ServerEvent(type="risk_update", risk_level=self.state.last_risk_level)
            yield gated
            return

        async for event in self._execute_plan(plan, transcript):
            yield event

    def _enforce_safety_gate(self, plan: ActionPlan, transcript: str) -> ServerEvent | None:
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

        if payment_intent and plan.action_type in {"navigate", "act", "extract"} and not plan.requires_confirmation:
            plan = plan.model_copy(
                update={
                    "requires_confirmation": True,
                    "confirmation_phrase": "yes, proceed safely",
                }
            )

        if plan.requires_confirmation:
            phrase = plan.confirmation_phrase or "yes, proceed safely"
            self.pending_plan = plan.model_copy(update={"requires_confirmation": False, "confirmation_phrase": None})
            self.state.pending_confirmation = True
            self.state.pending_confirmation_phrase = phrase
            self.state.last_risk_level = "HIGH_RISK"
            return ServerEvent(
                type="agent_response",
                text=(
                    "Safety check required before any risky step. "
                    f"Please say exactly: '{phrase}'."
                ),
            )

        # Block potentially submitting actions unless explicit confirmation state exists.
        if plan.action_type == "act" and plan.instruction:
            lowered = plan.instruction.lower()
            if any(token in lowered for token in ["submit", "place order", "pay now", "confirm payment"]):
                self.pending_plan = plan
                self.state.pending_confirmation = True
                self.state.pending_confirmation_phrase = "yes, proceed safely"
                self.state.last_risk_level = "HIGH_RISK"
                return ServerEvent(
                    type="agent_response",
                    text=(
                        "I am blocking this submission until explicit confirmation. "
                        "Please say exactly: 'yes, proceed safely'."
                    ),
                )

        return None

    async def _execute_plan(self, plan: ActionPlan, transcript: str) -> AsyncIterator[ServerEvent]:
        yield ServerEvent(
            type="status",
            text=f"Action: {plan.action_type} ({plan.reason})",
            metadata=self.runtime_info(),
        )

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

        risk_level: RiskLevel = self.brain.classify_risk(transcript=transcript, url=self.state.last_url)
        self.state.last_risk_level = risk_level
        yield ServerEvent(type="risk_update", risk_level=risk_level)

        if not result.success:
            yield ServerEvent(type="agent_response", text=result.message)
            return

        base_message = self._voice_message(risk_level)
        yield ServerEvent(type="agent_response", text=f"{base_message} {result.message}")

        if result.extracted_data is not None:
            yield ServerEvent(
                type="status",
                text="Extracted page data.",
                metadata={"extracted_data": result.extracted_data},
            )

    def _voice_message(self, risk_level: RiskLevel) -> str:
        if risk_level == "DANGER":
            return "Hold on. This page appears risky or deceptive."
        if risk_level == "HIGH_RISK":
            return "I found a high-risk step and will proceed carefully."
        if risk_level == "CAUTION":
            return "This page requests sensitive information."
        return "Navigation looks safe so far."
