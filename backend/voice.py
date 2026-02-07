from __future__ import annotations

import asyncio
import base64
from typing import Any


class VoiceSynthesizer:
    def __init__(self, api_key: str, enabled: bool = False, model_id: str = "sonic-3", voice_id: str = "") -> None:
        self.enabled = enabled and bool(api_key)
        self.model_id = model_id
        self.voice_id = voice_id
        self._client: Any = None

        if not self.enabled:
            return

        try:
            from cartesia import Cartesia

            self._client = Cartesia(api_key=api_key)
        except Exception:
            self._client = None
            self.enabled = False

    async def synthesize_base64(self, text: str) -> str | None:
        if not self.enabled or self._client is None or not text.strip():
            return None

        try:
            audio_bytes = await asyncio.to_thread(self._synthesize_bytes, text)
            return base64.b64encode(audio_bytes).decode("ascii")
        except Exception:
            return None

    def _synthesize_bytes(self, text: str) -> bytes:
        # Cartesia Python SDK call (blocking): run in thread via synthesize_base64.
        chunks = self._client.tts.bytes(
            model_id=self.model_id,
            transcript=text,
            voice={"mode": "id", "id": self.voice_id},
            language="en",
            output_format={"container": "wav", "sample_rate": 22050, "encoding": "pcm_f32le"},
        )
        return b"".join(chunks)
