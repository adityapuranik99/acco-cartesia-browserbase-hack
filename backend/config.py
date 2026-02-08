import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    allow_origins: str = os.getenv("ALLOW_ORIGINS", "*")

    # Phase 1+
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    cartesia_api_key: str = os.getenv("CARTESIA_API_KEY", os.getenv("CARTERSIA_API_KEY", ""))
    browserbase_api_key: str = os.getenv("BROWSERBASE_API_KEY", "")
    browserbase_project_id: str = os.getenv("BROWSERBASE_PROJECT_ID", "")
    model_api_key: str = os.getenv("MODEL_API_KEY", "")
    stagehand_model_name: str = os.getenv("STAGEHAND_MODEL_NAME", "anthropic/claude-sonnet-4-5")
    stagehand_timeout_sec: float = float(os.getenv("STAGEHAND_TIMEOUT_SEC", "12"))
    enable_stagehand: bool = os.getenv("ENABLE_STAGEHAND", "0").lower() in {"1", "true", "yes"}
    claude_timeout_sec: float = float(os.getenv("CLAUDE_TIMEOUT_SEC", "10"))
    enable_claude: bool = os.getenv("ENABLE_CLAUDE", "0").lower() in {"1", "true", "yes"}
    enable_fast_risk_model: bool = os.getenv("ENABLE_FAST_RISK_MODEL", "1").lower() in {"1", "true", "yes"}
    fast_risk_model_name: str = os.getenv("FAST_RISK_MODEL_NAME", "claude-3-5-haiku-20241022")
    fast_risk_timeout_sec: float = float(os.getenv("FAST_RISK_TIMEOUT_SEC", "2.2"))
    safe_payment_domains: str = os.getenv("SAFE_PAYMENT_DOMAINS", "pge.com,google.com")
    enable_cartesia_tts: bool = os.getenv("ENABLE_CARTESIA_TTS", "0").lower() in {"1", "true", "yes"}
    cartesia_model_id: str = os.getenv("CARTESIA_MODEL_ID", "sonic-3")
    cartesia_voice_id: str = os.getenv("CARTESIA_VOICE_ID", "f9836c6e-a0bd-460e-9d3c-f7299fa60f94")
    cartesia_voice_id_caution: str = os.getenv("CARTESIA_VOICE_ID_CAUTION", "")
    cartesia_voice_id_high_risk: str = os.getenv("CARTESIA_VOICE_ID_HIGH_RISK", "")
    cartesia_voice_id_danger: str = os.getenv("CARTESIA_VOICE_ID_DANGER", "")
    enable_cartesia_stt: bool = os.getenv("ENABLE_CARTESIA_STT", "0").lower() in {"1", "true", "yes"}
    cartesia_stt_model: str = os.getenv("CARTESIA_STT_MODEL", "ink-whisper")
    voice_mode: str = os.getenv("VOICE_MODE", "ptt").strip().lower()
    cartesia_line_agent_id: str = os.getenv("CARTESIA_LINE_AGENT_ID", "")
    exa_api_key: str = os.getenv("EXA_API_KEY", "")
    enable_exa_verification: bool = os.getenv("ENABLE_EXA_VERIFICATION", "0").lower() in {"1", "true", "yes"}
    demo_gmail_email: str = os.getenv("DEMO_GMAIL_EMAIL", "")
    demo_gmail_password: str = os.getenv("DEMO_GMAIL_PASSWORD", "")
    demo_pge_email: str = os.getenv("DEMO_PGE_EMAIL", "")
    demo_pge_password: str = os.getenv("DEMO_PGE_PASSWORD", "")


settings = Settings()
