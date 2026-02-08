from __future__ import annotations

import asyncio
import base64
from typing import Any


RISK_PROFILES: dict[str, dict[str, Any]] = {
    "SAFE": {
        "speed": "normal",
        "emotion": ["positivity:high"],
        "speed_scalar": 1.0,
    },
    "CAUTION": {
        "speed": "normal",
        "emotion": ["curiosity:high"],
        "speed_scalar": 0.95,
    },
    "High Risk": {
        "speed": "slow",
        "emotion": ["surprise:high", "sadness:low"],
        "speed_scalar": 0.85,
    },
    "DANGER": {
        "speed": "slowest",
        "emotion": ["anger:highest", "surprise:high"],
        "speed_scalar": 0.75,
    },
}


class VoiceSynthesizer:
    def __init__(
        self,
        api_key: str,
        enabled: bool = False,
        model_id: str = "sonic-3",
        voice_id: str = "",
        voice_id_caution: str = "",
        voice_id_high_risk: str = "",
        voice_id_danger: str = "",
    ) -> None:
        self.enabled = enabled and bool(api_key)
        self.model_id = model_id
        self.voice_id = voice_id
        self.voice_id_caution = voice_id_caution
        self.voice_id_high_risk = voice_id_high_risk
        self.voice_id_danger = voice_id_danger
        self._client: Any = None

        if not self.enabled:
            return

        try:
            from cartesia import Cartesia

            self._client = Cartesia(api_key=api_key)
        except Exception:
            self._client = None
            self.enabled = False

    async def synthesize_base64(self, text: str, risk_level: str = "SAFE") -> str | None:
        if not self.enabled or self._client is None or not text.strip():
            return None

        try:
            audio_bytes = await asyncio.to_thread(self._synthesize_bytes, text, risk_level)
            return base64.b64encode(audio_bytes).decode("ascii")
        except Exception:
            return None

    def _synthesize_bytes(self, text: str, risk_level: str) -> bytes:
        profile = RISK_PROFILES.get(risk_level, RISK_PROFILES["SAFE"])
        voice_id = self._voice_for_risk(risk_level)

        # Preferred path: use both speed and emotion controls.
        try:
            chunks = self._client.tts.bytes(
                model_id=self.model_id,
                transcript=text,
                voice={"mode": "id", "id": voice_id},
                language="en",
                speed=profile["speed"],
                generation_config={
                    "emotion": profile["emotion"],
                    "speed": profile["speed_scalar"],
                },
                output_format={"container": "wav", "sample_rate": 22050, "encoding": "pcm_f32le"},
            )
            return b"".join(chunks)
        except Exception:
            # Fallback: keep speed control, drop emotion config.
            chunks = self._client.tts.bytes(
                model_id=self.model_id,
                transcript=text,
                voice={"mode": "id", "id": voice_id},
                language="en",
                speed=profile["speed"],
                output_format={"container": "wav", "sample_rate": 22050, "encoding": "pcm_f32le"},
            )
            return b"".join(chunks)

    def _voice_for_risk(self, risk_level: str) -> str:
        if risk_level == "DANGER" and self.voice_id_danger:
            return self.voice_id_danger
        if risk_level == "High Risk" and self.voice_id_high_risk:
            return self.voice_id_high_risk
        if risk_level == "CAUTION" and self.voice_id_caution:
            return self.voice_id_caution
        return self.voice_id
