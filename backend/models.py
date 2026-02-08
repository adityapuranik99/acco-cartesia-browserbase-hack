from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

RiskLevel = Literal["SAFE", "CAUTION", "HIGH_RISK", "DANGER"]
EventType = Literal["agent_response", "risk_update", "browser_update", "status"]
ActionType = Literal["navigate", "act", "extract", "stop", "noop"]


class ClientMessage(BaseModel):
    type: Literal["user_speech"]
    transcript: str = Field(min_length=1)


class ServerEvent(BaseModel):
    type: EventType
    text: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    url: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionPlan(BaseModel):
    action_type: ActionType
    reason: str
    url: Optional[HttpUrl] = None
    instruction: Optional[str] = None
    service_name: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_phrase: Optional[str] = None


class ExecutionResult(BaseModel):
    success: bool
    message: str
    current_url: Optional[str] = None
    extracted_data: Optional[Any] = None


class PageSnapshot(BaseModel):
    current_url: str = "about:blank"
    title: Optional[str] = None
    dom_excerpt: Optional[str] = None
    screenshot_b64: Optional[str] = None
    visible_text_excerpt: Optional[str] = None
    form_fields: list[str] = Field(default_factory=list)
    payment_amount: Optional[str] = None
    payee_entity: Optional[str] = None
    urgency_signals: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    risk_level: RiskLevel
    risk_reasons: list[str] = Field(default_factory=list)
    recommended_action: Literal["proceed", "warn", "block"] = "proceed"
    voice_message: str
    requires_confirmation: bool = False
    confirmation_phrase: Optional[str] = None


class AgentState(BaseModel):
    current_goal: Optional[str] = None
    expected_service: Optional[str] = None
    pending_confirmation: bool = False
    pending_confirmation_phrase: Optional[str] = None
    last_risk_level: RiskLevel = "SAFE"
    last_url: str = "about:blank"
    action_history: list[str] = Field(default_factory=list)
    last_page_snapshot: Optional[dict[str, Any]] = None
