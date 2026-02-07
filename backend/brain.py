from __future__ import annotations

import asyncio
import json
from typing import Any

from models import ActionPlan, AgentState, RiskLevel


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
            return self._fallback_plan(transcript)

        try:
            response = await asyncio.wait_for(self._call_claude(transcript, state), timeout=self.timeout_sec)
            plan = self._extract_plan(response)
            if plan is not None:
                return plan
        except Exception:
            pass

        return self._fallback_plan(transcript)

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
            "and provide a specific confirmation phrase."
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

    def _fallback_plan(self, transcript: str) -> ActionPlan:
        lower = transcript.lower().strip()

        if "stop" in lower or "cancel" in lower:
            return ActionPlan(action_type="stop", reason="User asked to stop.")

        if "google" in lower:
            return ActionPlan(
                action_type="navigate",
                reason="User asked for Google.",
                url="https://www.google.com",
            )

        if "pge" in lower or "electric bill" in lower:
            return ActionPlan(
                action_type="navigate",
                reason="User asked to pay electricity bill.",
                url="https://pge-billing-urgent.vercel.app",
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
