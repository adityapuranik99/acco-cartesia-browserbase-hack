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
    safe_payment_domains: str = os.getenv("SAFE_PAYMENT_DOMAINS", "pge.com,google.com")
    enable_cartesia_tts: bool = os.getenv("ENABLE_CARTESIA_TTS", "0").lower() in {"1", "true", "yes"}
    cartesia_model_id: str = os.getenv("CARTESIA_MODEL_ID", "sonic-3")
    cartesia_voice_id: str = os.getenv("CARTESIA_VOICE_ID", "f786b574-daa5-4673-aa0c-cbe3e8534c02")
    cartesia_voice_id_caution: str = os.getenv("CARTESIA_VOICE_ID_CAUTION", "")
    cartesia_voice_id_high_risk: str = os.getenv("CARTESIA_VOICE_ID_HIGH_RISK", "")
    cartesia_voice_id_danger: str = os.getenv("CARTESIA_VOICE_ID_DANGER", "")
    enable_cartesia_stt: bool = os.getenv("ENABLE_CARTESIA_STT", "0").lower() in {"1", "true", "yes"}
    cartesia_stt_model: str = os.getenv("CARTESIA_STT_MODEL", "ink-whisper")
    exa_api_key: str = os.getenv("EXA_API_KEY", "")
    enable_exa_verification: bool = os.getenv("ENABLE_EXA_VERIFICATION", "0").lower() in {"1", "true", "yes"}


settings = Settings()
