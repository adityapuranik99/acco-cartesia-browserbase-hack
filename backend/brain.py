from __future__ import annotations

import asyncio
import json
from typing import Any

from models import ActionPlan, AgentState, PageSnapshot, RiskAssessment, RiskLevel


class Brain:
    def __init__(
        self,
        anthropic_api_key: str,
        timeout_sec: float = 10.0,
        enabled: bool = False,
        fast_risk_model_name: str = "claude-3-5-haiku-20241022",
        fast_risk_timeout_sec: float = 2.2,
        enable_fast_risk_model: bool = True,
    ) -> None:
        self.anthropic_api_key = anthropic_api_key
        self.timeout_sec = timeout_sec
        self.enabled = enabled
        self.fast_risk_model_name = fast_risk_model_name
        self.fast_risk_timeout_sec = fast_risk_timeout_sec
        self.enable_fast_risk_model = enable_fast_risk_model
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

    async def analyze_page_risk_fast(self, transcript: str, snapshot: PageSnapshot) -> RiskAssessment:
        """Fast risk pass: small model with short timeout, then deterministic fallback."""
        if self._client is None or not self.enable_fast_risk_model:
            return self._fallback_risk(transcript, snapshot)

        try:
            response = await asyncio.wait_for(
                self._call_claude_risk(
                    transcript,
                    snapshot,
                    model_name=self.fast_risk_model_name,
                    max_tokens=450,
                    include_image=False,
                ),
                timeout=self.fast_risk_timeout_sec,
            )
            risk = self._extract_risk(response)
            if risk is not None:
                return risk
        except Exception:
            pass

        return self._fallback_risk(transcript, snapshot)

    def classify_risk(self, transcript: str, url: str) -> RiskLevel:
        text = transcript.lower()
        url_text = (url or "").lower()
        if "urgent" in url_text or any(k in text for k in ["act now", "terminated", "suspended"]):
            return "DANGER"
        if any(k in text for k in ["pay", "payment", "card", "checkout", "bill"]):
            return "High Risk"
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

        system = """You're a friendly helper for blind users. They can't see - you're their eyes. Be conversational and helpful!

ACTIONS:
- navigate: Go to URL (set service_name for companies like "Google")
- act: "Click the Sign In button" or "Type text in the email field"
- extract: "What does this page say?" (USE THIS to read/describe pages!)
- stop: When stuck or need user guidance

CONFIRMATION ONLY FOR:
- Payment buttons (e.g., "Click Pay $50")
- Otherwise NO confirmation needed!

Be natural:
✓ User: "Book flight SF to Delhi" → extract to see what's on the page first
✓ User: "Click login" → just do it
✓ User: "What's on this page?" → extract the content
✗ Don't ask permission for normal actions"""

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

    async def _call_claude_risk(
        self,
        transcript: str,
        snapshot: PageSnapshot,
        model_name: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 1000,
        include_image: bool = True,
    ) -> Any:
        tools = [
            {
                "name": "report_risk_assessment",
                "description": "Classify page risk and produce a concise safety voice response.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "risk_level": {
                            "type": "string",
                            "enum": ["SAFE", "CAUTION", "High Risk", "DANGER"],
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

        system = """You're helping a blind user understand what's on the page. Be friendly and descriptive!

CLASSIFY RISK:
SAFE: Normal pages
CAUTION: Login/forms (NO confirmation needed!)
High Risk: Payment buttons (requires_confirmation=true)
DANGER: Scam signs - urgency language, domain mismatch

VOICE MESSAGE:
- Describe what you see naturally
- Include visible content, buttons, forms
- Be conversational like talking to a friend
- For payments, mention the amount
- For scams, warn clearly

Example messages:
SAFE: "I'm on google.com. I see a search bar and some trending topics. What do you want to search for?"
CAUTION: "I'm on the PG&E login page. I see username and password fields. What should I enter?"
High Risk: "I see a payment button for $142.50. Want me to click it?"
DANGER: "Whoa! This site looks fake - it has 'urgent' in the URL and countdown timers. That's a scam tactic!"

Require confirmation ONLY for payment clicks!"""

        payload = {
            "user_request": transcript,
            "snapshot": json.loads(snapshot.model_dump_json()),
        }

        content: list[dict[str, Any]] = [
            {"type": "text", "text": json.dumps(payload)},
        ]
        if include_image and snapshot.screenshot_b64:
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
            model=model_name,
            max_tokens=max_tokens,
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

        payment_terms = ["pay", "payment", "bill", "checkout"]
        payment_surface_signal = bool(snapshot.payment_amount) or "pay" in dom_text or any(
            token in url_text for token in ["checkout", "payment", "/pay", "billing"]
        )
        payment_intent_signal = any(k in text for k in payment_terms)

        if payment_surface_signal:
            if risk != "DANGER":
                risk = "High Risk"
                recommended_action = "warn"
            reasons.append("Payment-related interaction detected.")
            requires_confirmation = True
            confirmation_phrase = "yes, proceed safely"
        elif payment_intent_signal and risk == "SAFE":
            risk = "CAUTION"
            recommended_action = "warn"
            reasons.append("User requested a payment action; waiting for on-page payment signals.")

        if snapshot.form_fields and risk == "SAFE":
            risk = "CAUTION"
            recommended_action = "proceed"  # Changed from "warn" - login forms are OK
            reasons.append("Form fields requesting user information detected.")

        if not reasons:
            reasons.append("No immediate high-risk signals detected.")

        # Generate context-aware voice messages with action guidance
        if risk == "DANGER":
            if "urgent" in url_text or "suspend" in urgency_text:
                voice_message = (
                    "Stop. This page is using urgent language designed to pressure you into acting quickly. "
                    "Legitimate businesses don't create artificial urgency like this. "
                    "I strongly recommend we don't proceed here. Should I navigate to a verified website instead?"
                )
            else:
                voice_message = (
                    "I've detected multiple warning signs on this page that concern me. "
                    "This could be a scam or deceptive site. For your safety, I'm not going to continue here. "
                    "Would you like me to help you find the legitimate website?"
                )
        elif risk == "High Risk":
            amount_text = snapshot.payment_amount or "an amount"
            voice_message = (
                f"I've found a payment page requesting {amount_text}. "
                f"Before I proceed with any financial transaction, I need you to confirm this is correct and authorized. "
                f"Should I proceed to enter payment information, or would you like me to review the details first?"
            )
        elif risk == "CAUTION":
            if snapshot.form_fields:
                voice_message = f"I'm on {snapshot.current_url}. I see a login form here. Just tell me what to fill in!"
            else:
                voice_message = f"I'm on {snapshot.current_url}. The page looks fine."
        else:  # SAFE
            # Extract some visible content to narrate
            visible_preview = (snapshot.visible_text_excerpt or "")[:200] if snapshot.visible_text_excerpt else ""
            if visible_preview:
                voice_message = f"I'm on {snapshot.current_url}. I can see: {visible_preview}..."
            else:
                voice_message = f"I'm on {snapshot.current_url}. Ready to help!"

        return RiskAssessment(
            risk_level=risk,
            risk_reasons=reasons,
            recommended_action="block" if recommended_action == "block" else ("warn" if recommended_action == "warn" else "proceed"),
            voice_message=voice_message,
            requires_confirmation=requires_confirmation,
            confirmation_phrase=confirmation_phrase,
        )
