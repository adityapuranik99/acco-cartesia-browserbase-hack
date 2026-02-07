from __future__ import annotations

import asyncio
from typing import Any


class SpeechTranscriber:
    def __init__(self, api_key: str, enabled: bool = False, model: str = "ink-whisper") -> None:
        self.enabled = enabled and bool(api_key)
        self.model = model
        self._client: Any = None

        if not self.enabled:
            return

        try:
            from cartesia import Cartesia

            self._client = Cartesia(api_key=api_key)
        except Exception:
            self._client = None
            self.enabled = False

    async def transcribe_bytes(self, audio_bytes: bytes, filename: str, content_type: str | None = None) -> str:
        if not self.enabled or self._client is None:
            return ""
        if not audio_bytes:
            return ""

        try:
            response = await asyncio.to_thread(self._transcribe_sync, audio_bytes, filename, content_type)
            text = getattr(response, "text", "")
            return text.strip() if isinstance(text, str) else ""
        except Exception:
            return ""

    def _transcribe_sync(self, audio_bytes: bytes, filename: str, content_type: str | None = None) -> Any:
        file_payload = (filename, audio_bytes, content_type or "application/octet-stream")
        return self._client.stt.transcribe(
            file=file_payload,
            model=self.model,
        )
