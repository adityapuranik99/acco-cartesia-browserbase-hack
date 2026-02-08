import json
from contextlib import suppress
import asyncio
from urllib import error as urllib_error
from urllib import request as urllib_request

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent import AccessibilityCopilot
from config import settings
from models import ClientMessage
from stt import SpeechTranscriber
from ui_channel import ui_event_channel
from voice import VoiceSynthesizer

app = FastAPI(title="Accessibility Co-Pilot Backend", version="0.2.0")

origins = [origin.strip() for origin in settings.allow_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/stt")
async def stt_transcribe(audio: UploadFile = File(...)) -> dict[str, str]:
    transcriber = SpeechTranscriber(
        api_key=settings.cartesia_api_key,
        enabled=settings.enable_cartesia_stt,
        model=settings.cartesia_stt_model,
    )
    if not transcriber.enabled:
        raise HTTPException(status_code=400, detail="Cartesia STT is disabled.")

    data = await audio.read()
    transcript = await transcriber.transcribe_bytes(
        audio_bytes=data,
        filename=audio.filename or "audio.webm",
        content_type=audio.content_type,
    )
    if not transcript:
        raise HTTPException(status_code=422, detail="No transcript returned.")
    return {"transcript": transcript}


@app.post("/cartesia/access-token")
async def create_cartesia_access_token(payload: dict[str, int | bool] | None = None) -> dict[str, object]:
    if not settings.cartesia_api_key:
        raise HTTPException(status_code=400, detail="CARTESIA_API_KEY is not configured.")

    body = payload or {}
    expires_in = int(body.get("expires_in", 600))
    expires_in = max(60, min(expires_in, 3600))
    grant_agent = bool(body.get("grant_agent", True))
    grant_tts = bool(body.get("grant_tts", True))
    grant_stt = bool(body.get("grant_stt", True))

    request_payload: dict[str, object] = {
        "expires_in": expires_in,
        "grants": {
            "agent": grant_agent,
            "tts": grant_tts,
            "stt": grant_stt,
        },
    }

    req = urllib_request.Request(
        url="https://api.cartesia.ai/access-token",
        data=json.dumps(request_payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.cartesia_api_key}",
            "X-API-Key": settings.cartesia_api_key,
            "Cartesia-Version": "2025-04-16",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
        token_payload = json.loads(raw)
        if not isinstance(token_payload, dict):
            raise HTTPException(status_code=502, detail="Unexpected Cartesia token response format.")
        return token_payload
    except urllib_error.HTTPError as exc:
        detail = "Cartesia token request failed."
        status = 502
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8")
            parsed = json.loads(error_body)
            if isinstance(parsed, dict):
                error_value = parsed.get("error")
                if isinstance(error_value, dict):
                    detail = error_value.get("message") or parsed.get("message") or detail
                elif isinstance(error_value, str) and error_value.strip():
                    detail = error_value
                else:
                    message = parsed.get("message")
                    if isinstance(message, str) and message.strip():
                        detail = message
                cartesia_status = parsed.get("status")
                if isinstance(cartesia_status, int):
                    status = cartesia_status
        except Exception:
            pass
        if error_body and detail == "Cartesia token request failed.":
            detail = error_body[:500]
        if 400 <= exc.code < 500:
            status = exc.code
        detail = f"Cartesia /access-token {exc.code}: {detail}"
        raise HTTPException(status_code=status, detail=detail) from exc
    except urllib_error.URLError as exc:
        raise HTTPException(status_code=502, detail="Unable to reach Cartesia token endpoint.") from exc


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    voice = VoiceSynthesizer(
        api_key=settings.cartesia_api_key,
        enabled=settings.enable_cartesia_tts,
        model_id=settings.cartesia_model_id,
        voice_id=settings.cartesia_voice_id,
        voice_id_caution=settings.cartesia_voice_id_caution,
        voice_id_high_risk=settings.cartesia_voice_id_high_risk,
        voice_id_danger=settings.cartesia_voice_id_danger,
    )

    copilot = AccessibilityCopilot(
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
            d.strip().lower() for d in settings.safe_payment_domains.split(",") if d.strip()
        ],
        demo_gmail_email=settings.demo_gmail_email,
        demo_gmail_password=settings.demo_gmail_password,
        demo_pge_email=settings.demo_pge_email,
        demo_pge_password=settings.demo_pge_password,
    )
    await copilot.start()

    await websocket.send_text(
        json.dumps({"type": "status", "text": "connected", "metadata": copilot.runtime_info()})
    )

    try:
        current_risk_level = "SAFE"
        current_task: asyncio.Task[None] | None = None

        async def process_transcript(transcript: str) -> None:
            nonlocal current_risk_level
            async for event in copilot.handle_transcript(transcript):
                if event.type == "risk_update" and event.risk_level:
                    current_risk_level = event.risk_level
                if event.type == "agent_response" and event.text:
                    audio_b64 = await voice.synthesize_base64(event.text or "", risk_level=current_risk_level)
                    if audio_b64:
                        event.metadata["audio_b64"] = audio_b64
                        event.metadata["audio_mime"] = "audio/wav"
                        event.metadata["voice_risk_profile"] = current_risk_level
                payload = event.model_dump_json()
                await websocket.send_text(payload)
                await ui_event_channel.publish(payload)

        while True:
            payload = await websocket.receive_json()
            msg = ClientMessage.model_validate(payload)
            if msg.type == "interrupt":
                if current_task and not current_task.done():
                    current_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await current_task
                await websocket.send_text(
                    json.dumps({"type": "status", "text": "Interrupted current action by user request."})
                )
                continue

            if current_task and not current_task.done():
                current_task.cancel()
                with suppress(asyncio.CancelledError):
                    await current_task

            current_task = asyncio.create_task(process_transcript(msg.transcript or ""))
    except WebSocketDisconnect:
        return
    finally:
        if "current_task" in locals() and current_task and not current_task.done():
            current_task.cancel()
            with suppress(asyncio.CancelledError):
                await current_task
        await copilot.shutdown()


@app.websocket("/ws/ui")
async def websocket_ui_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await ui_event_channel.subscribe()
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "status",
                    "text": "connected",
                    "metadata": {"voice_mode": settings.voice_mode},
                }
            )
        )
        while True:
            payload = await queue.get()
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        return
    finally:
        await ui_event_channel.unsubscribe(queue)


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=True)
