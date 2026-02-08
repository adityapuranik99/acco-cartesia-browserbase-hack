from __future__ import annotations

from typing import Any

from agent import AccessibilityCopilot
from config import settings
from ui_channel import ui_event_channel


class AccessibilityCopilotLineAgent:
    """
    Cartesia Line wrapper around the existing AccessibilityCopilot pipeline.

    This keeps the current safety + browser logic unchanged and only swaps
    audio transport/turn handling to Line.
    """

    def __init__(self) -> None:
        self._copilot = AccessibilityCopilot(
            anthropic_api_key=settings.anthropic_api_key,
            browserbase_api_key=settings.browserbase_api_key,
            browserbase_project_id=settings.browserbase_project_id,
            model_api_key=settings.model_api_key,
            stagehand_model_name=settings.stagehand_model_name,
            stagehand_timeout_sec=settings.stagehand_timeout_sec,
            enable_stagehand=settings.enable_stagehand,
            claude_timeout_sec=settings.claude_timeout_sec,
            enable_claude=settings.enable_claude,
            enable_fast_risk_model=settings.enable_fast_risk_model,
            fast_risk_model_name=settings.fast_risk_model_name,
            fast_risk_timeout_sec=settings.fast_risk_timeout_sec,
            exa_api_key=settings.exa_api_key,
            enable_exa_verification=settings.enable_exa_verification,
            safe_payment_domains=[
                domain.strip().lower() for domain in settings.safe_payment_domains.split(",") if domain.strip()
            ],
            demo_gmail_email=settings.demo_gmail_email,
            demo_gmail_password=settings.demo_gmail_password,
            demo_pge_email=settings.demo_pge_email,
            demo_pge_password=settings.demo_pge_password,
        )
        self._started = False

    async def process(self, env: Any, event: Any):  # pragma: no cover - runtime callback
        event_name = event.__class__.__name__

        if event_name == "CallStarted":
            if not self._started:
                await self._copilot.start()
                self._started = True
            await self._publish_status("connected", metadata=self._copilot.runtime_info())
            yield self._make_agent_send_text(
                "Hi there. I'm your accessibility co-pilot. "
                "Tell me what website or task you want help with."
            )
            return

        if event_name == "UserTurnEnded":
            user_text = self._extract_user_text(event)
            if not user_text:
                return

            async for server_event in self._copilot.handle_transcript(user_text):
                await ui_event_channel.publish(server_event.model_dump_json())
                if server_event.type == "agent_response" and server_event.text:
                    yield self._make_agent_send_text(server_event.text)
            return

        if event_name == "CallEnded":
            await self._shutdown()
            await self._publish_status("call_ended")

    async def _shutdown(self) -> None:
        if not self._started:
            return
        await self._copilot.shutdown()
        self._started = False

    @staticmethod
    def _extract_user_text(event: Any) -> str:
        for attr in ("transcript", "text"):
            value = getattr(event, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()

        content = getattr(event, "content", None)
        if not isinstance(content, list):
            return ""

        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
                continue
            for attr in ("content", "text", "transcript"):
                value = getattr(item, attr, None)
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
                    break
        return " ".join(parts).strip()

    @staticmethod
    def _make_agent_send_text(text: str) -> Any:
        from line.events import AgentSendText

        return AgentSendText(text=text)

    @staticmethod
    async def _publish_status(text: str, metadata: dict[str, Any] | None = None) -> None:
        payload = {
            "type": "status",
            "text": text,
            "metadata": metadata or {},
        }
        import json

        await ui_event_channel.publish(json.dumps(payload))


async def get_agent(env: Any, call_request: Any) -> AccessibilityCopilotLineAgent:
    return AccessibilityCopilotLineAgent()


def build_voice_agent_app() -> Any:
    try:
        from line.voice_agent_app import VoiceAgentApp
    except Exception as exc:  # pragma: no cover - import guard for optional dependency
        raise RuntimeError(
            "Cartesia Line SDK is required for this runtime. Install it with `pip install cartesia-line`."
        ) from exc

    return VoiceAgentApp(get_agent=get_agent)


if __name__ == "__main__":
    build_voice_agent_app().run()
