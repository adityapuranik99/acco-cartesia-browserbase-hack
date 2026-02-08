from __future__ import annotations

import asyncio
import json
from typing import Any

from models import ActionPlan, AgentState, PageSnapshot, RiskAssessment, RiskLevel


class Brain:
    def __init__(self, anthropic_api_key: str, timeout_sec: float = 10.0, enabled: bool = False) -> None:
        self.anthropic_api_key = anthropic_api_key
        self.timeout_sec = timeout_sec
        self.enabled = enabled
        self._client: Any = None

        if enabled and anthropic_api_key:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(
                    api_key=anthropic_api_key,
                    timeout=self.timeout_sec,
                )
            except Exception:
                self._client = None

    async def plan_action(self, transcript: str, state: AgentState) -> ActionPlan:
        if self._client is None:
            return self._fallback_plan(transcript, state)

        try:
            response = await asyncio.wait_for(self._call_claude(transcript, state), timeout=self.timeout_sec)
            plan = self._extract_plan(response)
            if plan is not None:
                return plan
        except Exception:
            pass

        return self._fallback_plan(transcript, state)

    async def analyze_page_risk(self, transcript: str, snapshot: PageSnapshot) -> RiskAssessment:
        if self._client is None:
            return self._fallback_risk(transcript, snapshot)

        try:
            response = await asyncio.wait_for(self._call_claude_risk(transcript, snapshot), timeout=self.timeout_sec)
            risk = self._extract_risk(response)
            if risk is not None:
                return risk
        except Exception:
            pass

        return self._fallback_risk(transcript, snapshot)

    def analyze_page_risk_fast(self, transcript: str, snapshot: PageSnapshot) -> RiskAssessment:
        """Fast deterministic pass used to provide immediate risk feedback."""
        return self._fallback_risk(transcript, snapshot)

    def classify_risk(self, transcript: str, url: str) -> RiskLevel:
        text = transcript.lower()
        url_text = (url or "").lower()
        if "urgent" in url_text or any(k in text for k in ["act now", "terminated", "suspended"]):
            return "DANGER"
        if any(k in text for k in ["pay", "payment", "card", "checkout", "bill"]):
            return "HIGH_RISK"
        if any(k in text for k in ["account", "login", "personal", "ssn"]):
            return "CAUTION"
        return "SAFE"

    async def _call_claude(self, transcript: str, state: AgentState) -> Any:
        tools = [
            {
                "name": "propose_action",
                "description": "Propose exactly one next browser action.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action_type": {
                            "type": "string",
                            "enum": ["navigate", "act", "extract", "stop", "noop"],
                        },
                        "reason": {"type": "string"},
                        "url": {"type": "string"},
                        "instruction": {"type": "string"},
                        "service_name": {"type": "string"},
                        "requires_confirmation": {"type": "boolean"},
                        "confirmation_phrase": {"type": "string"},
                    },
                    "required": ["action_type", "reason", "requires_confirmation"],
                },
            }
        ]

        system = (
            "You are an accessibility-safe web automation planner. "
            "Only output one tool call with a conservative action. "
            "If a payment or submission might occur, set requires_confirmation=true "
            "and provide a specific confirmation phrase. "
            "When interacting with a specific company/service, set service_name. "
            "Do not repeat the same action from action_history. "
            "Prefer progressing in short steps toward the current goal."
        )

        user_content = {
            "transcript": transcript,
            "state": json.loads(state.model_dump_json()),
        }

        return await self._client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=800,
            tools=tools,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": json.dumps(user_content)}],
                }
            ],
        )

    async def _call_claude_risk(self, transcript: str, snapshot: PageSnapshot) -> Any:
        tools = [
            {
                "name": "report_risk_assessment",
                "description": "Classify page risk and produce a concise safety voice response.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "risk_level": {
                            "type": "string",
                            "enum": ["SAFE", "CAUTION", "HIGH_RISK", "DANGER"],
                        },
                        "risk_reasons": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "recommended_action": {
                            "type": "string",
                            "enum": ["proceed", "warn", "block"],
                        },
                        "voice_message": {"type": "string"},
                        "requires_confirmation": {"type": "boolean"},
                        "confirmation_phrase": {"type": "string"},
                    },
                    "required": ["risk_level", "risk_reasons", "recommended_action", "voice_message", "requires_confirmation"],
                },
            }
        ]

        system = (
            "You are a web safety analyzer for vulnerable users. "
            "Use URL/domain clues, urgency language, payment prompts, and form requests "
            "to classify risk conservatively. "
            "If payment submission risk exists, require confirmation."
        )

        payload = {
            "user_request": transcript,
            "snapshot": json.loads(snapshot.model_dump_json()),
        }

        content: list[dict[str, Any]] = [
            {"type": "text", "text": json.dumps(payload)},
        ]
        if snapshot.screenshot_b64:
            content.insert(
                0,
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": snapshot.screenshot_b64,
                    },
                },
            )

        return await self._client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            tools=tools,
            system=system,
            messages=[{"role": "user", "content": content}],
        )

    def _extract_plan(self, response: Any) -> ActionPlan | None:
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "propose_action":
                payload = getattr(block, "input", None)
                if isinstance(payload, dict):
                    try:
                        return ActionPlan.model_validate(payload)
                    except Exception:
                        return None
        return None

    def _extract_risk(self, response: Any) -> RiskAssessment | None:
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "report_risk_assessment":
                payload = getattr(block, "input", None)
                if isinstance(payload, dict):
                    try:
                        return RiskAssessment.model_validate(payload)
                    except Exception:
                        return None
        return None

    def _fallback_plan(self, transcript: str, state: AgentState) -> ActionPlan:
        lower = transcript.lower().strip()
        current_url = (state.last_url or "").lower()

        if "stop" in lower or "cancel" in lower:
            return ActionPlan(action_type="stop", reason="User asked to stop.")

        if state.action_history and any(k in lower for k in ["done", "finished", "thank you"]):
            return ActionPlan(action_type="stop", reason="User indicated completion.")

        if "google" in lower:
            return ActionPlan(
                action_type="navigate",
                reason="User asked for Google.",
                url="https://www.google.com",
                service_name="Google",
            )

        if "pge" in lower or "electric bill" in lower:
            if "pge.com" in current_url:
                return ActionPlan(
                    action_type="act",
                    reason="Continue bill-pay flow on verified utility site.",
                    instruction="Click the bill payment or login action that continues payment flow.",
                    requires_confirmation=False,
                )
            return ActionPlan(
                action_type="navigate",
                reason="User asked to pay electricity bill.",
                url="https://www.pge.com",
                service_name="PG&E",
                requires_confirmation=True,
                confirmation_phrase="yes, proceed safely",
            )

        if "pay" in lower:
            return ActionPlan(
                action_type="noop",
                reason="Detected payment intent.",
                requires_confirmation=True,
                confirmation_phrase="yes, pay 142 dollars and 50 cents",
            )

        return ActionPlan(action_type="noop", reason="No direct browser action inferred.")

    def _fallback_risk(self, transcript: str, snapshot: PageSnapshot) -> RiskAssessment:
        text = transcript.lower()
        url_text = (snapshot.current_url or "").lower()
        urgency_text = " ".join(snapshot.urgency_signals).lower()
        dom_text = (snapshot.visible_text_excerpt or "").lower()

        reasons: list[str] = []
        risk: RiskLevel = "SAFE"
        recommended_action: str = "proceed"
        requires_confirmation = False
        confirmation_phrase: str | None = None

        if "urgent" in url_text or "suspend" in urgency_text or "act now" in urgency_text:
            risk = "DANGER"
            recommended_action = "block"
            reasons.append("Urgency or scare-tactic signals detected.")

        if snapshot.payment_amount or any(k in text for k in ["pay", "payment", "bill", "checkout"]) or "pay" in dom_text:
            if risk != "DANGER":
                risk = "HIGH_RISK"
                recommended_action = "warn"
            reasons.append("Payment-related interaction detected.")
            requires_confirmation = True
            confirmation_phrase = "yes, proceed safely"

        if snapshot.form_fields and risk == "SAFE":
            risk = "CAUTION"
            recommended_action = "warn"
            reasons.append("Form fields requesting user information detected.")

        if not reasons:
            reasons.append("No immediate high-risk signals detected.")

        voice_message = {
            "SAFE": "This page looks safe so far.",
            "CAUTION": "This page requests information, so I will proceed carefully.",
            "HIGH_RISK": "This appears to be a payment step. I need confirmation before continuing.",
            "DANGER": "This page looks suspicious. I recommend blocking this action.",
        }[risk]

        return RiskAssessment(
            risk_level=risk,
            risk_reasons=reasons,
            recommended_action="block" if recommended_action == "block" else ("warn" if recommended_action == "warn" else "proceed"),
            voice_message=voice_message,
            requires_confirmation=requires_confirmation,
            confirmation_phrase=confirmation_phrase,
        )
