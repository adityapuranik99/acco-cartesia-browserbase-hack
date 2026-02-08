# Cartesia Line Integration — Implementation Plan

> **Goal**: Swap in Cartesia Line as a modular voice backend, replacing the current
> push-to-talk + REST STT + queued TTS pipeline with a real-time streaming voice agent.
> The existing pipeline MUST remain functional as a fallback.

---

## 1. Why Line?

| Current Pipeline | With Line |
|---|---|
| User holds button → records blob → POST `/stt` → wait for transcript → agent processes → Sonic TTS generates full audio → wait → play | User speaks → Line streams audio in real-time via WebSocket → agent responds → Line streams Sonic TTS back with sub-40ms first byte |
| Turn-based, multiple seconds of dead air | Continuous conversation with natural turn-taking |
| Manual interruption handling | Built-in interruption + turn detection |
| Push-to-talk required | Always-listening with voice activity detection |

---

## 2. Architecture: Modular Swap Design

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                        │
│                                                             │
│  ┌──────────────────┐    ┌───────────────────────────────┐ │
│  │ VoicePanel        │    │ BrowserView                   │ │
│  │                   │    │ (Browserbase embed)           │ │
│  │ Mode A: PTT       │    │                               │ │
│  │  (existing blob    │    │                               │ │
│  │   record + REST)   │    │                               │ │
│  │                   │    │                               │ │
│  │ Mode B: Line      │    │                               │ │
│  │  (WebSocket stream │    │                               │ │
│  │   to Cartesia API) │    │                               │ │
│  └──────────────────┘    └───────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
          │ Mode A              │ Mode B
          ▼                     ▼
┌──────────────────┐   ┌─────────────────────────────┐
│ Our Backend      │   │ Cartesia Line Platform       │
│ /ws + /stt       │   │ wss://api.cartesia.ai/...    │
│ (FastAPI)        │   │                               │
│                  │   │  Line Agent (our code)        │
│ Agent + Brain    │   │   ├── process(env, event)     │
│ + Stagehand      │   │   ├── tools: browser actions  │
│ + VoiceSynth     │   │   └── LLM: Claude             │
└──────────────────┘   └─────────────────────────────┘
```

### Key Principle: The Line agent wraps our existing `AccessibilityCopilot`

Line does NOT replace our agent logic. It replaces the **audio transport layer**.
Our `Brain`, `BrowserController`, `DomainVerifier`, and safety logic stay identical.

---

## 3. Cartesia Line SDK Overview

### Installation

```bash
uv add cartesia-line
# or
pip install cartesia-line
```

### Core Concepts

| Concept | Description |
|---|---|
| `VoiceAgentApp` | Entry point. Wraps an agent factory function. Handles audio I/O. |
| `LlmAgent` | Built-in agent that wraps any LLM (100+ providers via LiteLLM). |
| `LlmConfig` | System prompt, introduction message, temperature, etc. |
| `Custom Agent` | Class with `async process(self, env, event)` that yields output events. |
| `@loopback_tool` | Tool whose result goes back to the LLM for natural language response. |
| `@passthrough_tool` | Tool whose output goes directly to the user (deterministic). |
| `agent_as_handoff` | Route conversation between specialized agents. |

### Event Model

**Input Events** (received by agent):
- `CallStarted` — Call/session initiated
- `UserTurnEnded` — User finished speaking (includes transcript)
- `UserTurnStarted` — User started speaking (can interrupt agent)
- `CallEnded` — Session terminated

**Output Events** (yielded by agent):
- `AgentSendText` — Text to be spoken via Sonic TTS
- `AgentTransferCall` — Route to phone number
- `LogMetric` / `LogMessage` — Observability

### Minimal Example

```python
import os
from line.llm_agent import LlmAgent, LlmConfig, end_call
from line.voice_agent_app import VoiceAgentApp

async def get_agent(env, call_request):
    return LlmAgent(
        model="anthropic/claude-sonnet-4-5",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        tools=[end_call],
        config=LlmConfig(
            system_prompt="You are a helpful voice assistant.",
            introduction="Hello! How can I help you today?",
        ),
    )

app = VoiceAgentApp(get_agent=get_agent)

if __name__ == "__main__":
    app.run()
```

---

## 4. Implementation Plan

### Phase 1: Line Agent Wrapper (Backend)

**New file: `backend/line_agent.py`**

Create a custom Line agent that wraps our existing `AccessibilityCopilot`:

```python
import os
from line.agent import TurnEnv
from line.events import (
    InputEvent, OutputEvent, CallStarted, UserTurnEnded,
    UserTurnStarted, CallEnded, AgentSendText,
)
from line.llm_agent import LlmAgent, LlmConfig, loopback_tool, passthrough_tool
from line.voice_agent_app import VoiceAgentApp

from agent import AccessibilityCopilot
from config import settings
from models import ServerEvent


class AccessibilityCopilotLineAgent:
    """
    Wraps our existing AccessibilityCopilot as a Cartesia Line agent.

    The Line SDK handles:
    - Real-time audio streaming (mic in, voice out)
    - Turn detection and interruption
    - Sonic TTS with emotion/speed controls

    Our agent handles:
    - Browser automation (Stagehand/Browserbase)
    - Risk analysis (Claude fast + deep)
    - Safety gates and confirmation flow
    - Domain verification (Exa)
    """

    def __init__(self):
        self.copilot = AccessibilityCopilot(
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
                d.strip().lower()
                for d in settings.safe_payment_domains.split(",")
                if d.strip()
            ],
        )
        self._started = False

    async def process(self, env: TurnEnv, event: InputEvent):
        if isinstance(event, CallStarted):
            if not self._started:
                await self.copilot.start()
                self._started = True
            yield AgentSendText(
                text="Hi there! I'm your accessibility co-pilot. "
                     "I can help you navigate the web safely. "
                     "What would you like to do today?"
            )

        elif isinstance(event, UserTurnEnded):
            # Extract transcript from the event
            user_text = " ".join(
                item.content for item in event.content
                if hasattr(item, "content")
            )
            if not user_text.strip():
                return

            # Process through our existing agent pipeline
            async for server_event in self.copilot.handle_transcript(user_text):
                if server_event.type == "agent_response" and server_event.text:
                    yield AgentSendText(text=server_event.text)
                # risk_update, status, voice_state etc. are internal —
                # we could forward them to a parallel WebSocket for the UI

        elif isinstance(event, CallEnded):
            if self._started:
                await self.copilot.shutdown()
                self._started = False


async def get_agent(env, call_request):
    return AccessibilityCopilotLineAgent()


app = VoiceAgentApp(get_agent=get_agent)
```

### Phase 2: Tool-Based Approach (Alternative)

Instead of wrapping the whole copilot, expose browser actions as Line tools:

```python
from line.llm_agent import LlmAgent, LlmConfig, loopback_tool, passthrough_tool, end_call

# Browser controller instance (shared)
browser = None  # initialized in get_agent

@loopback_tool
async def navigate_to_url(ctx, url: str) -> str:
    """Navigate the browser to a URL."""
    result = await browser.navigate(url)
    return f"Navigated to {result.current_url}. {result.message}"

@loopback_tool
async def click_or_type(ctx, instruction: str) -> str:
    """Perform a browser action like clicking a button or typing text."""
    result = await browser.act(instruction)
    return result.message

@loopback_tool
async def read_page(ctx, question: str) -> str:
    """Extract information from the current page."""
    result = await browser.extract(question)
    return result.extracted_data or result.message

@loopback_tool(is_background=True)
async def check_page_safety(ctx, url: str) -> str:
    """Analyze the current page for scam/risk indicators."""
    # Run risk analysis pipeline
    snapshot = await browser.capture_snapshot()
    assessment = await brain.analyze_page_risk_deep(transcript="", snapshot=snapshot)
    return (
        f"Risk level: {assessment.risk_level}. "
        f"Reasons: {', '.join(assessment.risk_reasons)}. "
        f"{assessment.voice_message}"
    )

async def get_agent(env, call_request):
    global browser
    # Initialize browser controller...

    return LlmAgent(
        model="anthropic/claude-sonnet-4-5",
        api_key=settings.anthropic_api_key,
        tools=[navigate_to_url, click_or_type, read_page, check_page_safety, end_call],
        config=LlmConfig(
            system_prompt=ACCESSIBILITY_COPILOT_SYSTEM_PROMPT,
            introduction="Hi! I'm your accessibility co-pilot. What can I help you with?",
            temperature=0.3,
        ),
    )
```

### Phase 3: Frontend Integration

**New file: `frontend/src/hooks/useLineVoice.js`**

The frontend connects directly to Cartesia's WebSocket for audio streaming:

```javascript
// WebSocket connection to Cartesia Line agent
const CARTESIA_WS_URL = 'wss://api.cartesia.ai/agents/stream';

export function useLineVoice(agentId, accessToken) {
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const connect = useCallback(async () => {
    // 1. Get microphone stream
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaStreamRef.current = stream;

    // 2. Connect to Line WebSocket
    const ws = new WebSocket(
      `${CARTESIA_WS_URL}/${agentId}`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Cartesia-Version': '2025-04-16',
        },
      }
    );

    ws.onopen = () => {
      setIsConnected(true);
      // Send start event with audio format config
      ws.send(JSON.stringify({
        type: 'start',
        config: {
          input_audio_format: 'pcm_16000',
          // output handled by Cartesia
        },
      }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'media_output') {
        // Play agent audio response
        playAudioChunk(data.payload);
        setIsSpeaking(true);
      }

      if (data.type === 'agent_turn_ended') {
        setIsSpeaking(false);
      }
    };

    // 3. Stream microphone audio to WebSocket
    const audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      const pcmData = e.inputBuffer.getChannelData(0);
      const base64 = pcmToBase64(pcmData);
      ws.send(JSON.stringify({
        type: 'media_input',
        payload: base64,
      }));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    wsRef.current = ws;
    audioContextRef.current = audioContext;
  }, [agentId, accessToken]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    mediaStreamRef.current?.getTracks().forEach(t => t.stop());
    audioContextRef.current?.close();
    setIsConnected(false);
  }, []);

  return { isConnected, isSpeaking, connect, disconnect };
}
```

### Phase 4: Config Toggle

**Updated `backend/config.py`**:

```python
# Voice mode: "ptt" (push-to-talk, current) or "line" (Cartesia Line)
voice_mode: str = os.getenv("VOICE_MODE", "ptt")
cartesia_line_agent_id: str = os.getenv("CARTESIA_LINE_AGENT_ID", "")
```

**Updated `frontend/.env`**:

```bash
VITE_VOICE_MODE=ptt          # or "line"
VITE_CARTESIA_LINE_AGENT_ID=
VITE_CARTESIA_ACCESS_TOKEN=
```

**Updated `VoicePanel.jsx`**:

```jsx
const voiceMode = import.meta.env.VITE_VOICE_MODE || 'ptt';

// Conditionally render PTT or Line mode
{voiceMode === 'ptt' ? (
  <PushToTalkControls ... />   // existing mic button + visualizer
) : (
  <LineVoiceControls ... />    // always-listening, no button needed
)}
```

---

## 5. Bridging Line ↔ Frontend UI

The challenge: Line handles voice I/O directly, but our frontend also needs:
- Risk level updates (for the badge)
- Browser view URL (for the iframe)
- Activity log events
- Voice state transitions

### Solution: Dual WebSocket

```
Frontend
  ├── WS 1: Cartesia Line (audio streaming) ← new
  └── WS 2: Our backend /ws (UI state updates) ← keep existing
```

The Line agent, when processing events, also pushes state updates
to our backend via an internal channel (Redis, in-memory queue, or
direct WebSocket relay). The frontend's existing `/ws` connection
continues to receive `risk_update`, `browser_update`, `status`, and
`voice_state` events.

```python
# Inside AccessibilityCopilotLineAgent.process():
async for server_event in self.copilot.handle_transcript(user_text):
    if server_event.type == "agent_response" and server_event.text:
        # This goes through Line → Sonic TTS → user hears it
        yield AgentSendText(text=server_event.text)

    # Forward non-voice events to the UI WebSocket
    await self._ui_channel.send(server_event.model_dump_json())
```

---

## 6. Deployment Options

### Option A: Self-Hosted (Demo)

Run the Line agent locally alongside our existing backend:

```bash
# Terminal 1: Existing backend (browser automation + UI WebSocket)
cd backend && python main.py

# Terminal 2: Line agent (voice I/O)
cd backend && ANTHROPIC_API_KEY=... python line_agent.py
```

Test locally with Cartesia CLI:
```bash
cartesia chat 8001
```

### Option B: Cartesia Cloud (Production)

Deploy the Line agent to Cartesia's managed runtime:

```bash
cd backend
cartesia init          # link to Cartesia agent
cartesia deploy        # deploy to cloud
cartesia env set ANTHROPIC_API_KEY=...
cartesia env set BROWSERBASE_API_KEY=...
```

The frontend connects to `wss://api.cartesia.ai/agents/stream/{agent_id}`.

---

## 7. Migration Checklist

### Backend

- [ ] `pip install cartesia-line`
- [ ] Create `backend/line_agent.py` with custom agent wrapping `AccessibilityCopilot`
- [ ] Add `VOICE_MODE` toggle to `config.py`
- [ ] Add internal channel for forwarding UI state events
- [ ] Test Line agent with `cartesia chat` CLI
- [ ] Ensure existing `/ws` + `/stt` endpoints remain untouched

### Frontend

- [ ] Create `useLineVoice.js` hook for WebSocket audio streaming
- [ ] Create `LineVoiceControls` component (always-listening mode)
- [ ] Add `VITE_VOICE_MODE` toggle in VoicePanel
- [ ] Handle dual WebSocket (Line for audio, backend for UI state)
- [ ] Keep existing PTT mode fully functional

### Testing

- [ ] PTT mode works exactly as before when `VOICE_MODE=ptt`
- [ ] Line mode connects and streams audio when `VOICE_MODE=line`
- [ ] Risk badges update correctly in both modes
- [ ] Browser view iframe works in both modes
- [ ] Activity log receives events in both modes
- [ ] Interruption works (user speaks while agent is talking)
- [ ] Greeting plays on connect in Line mode
- [ ] Safety confirmation flow works via voice in Line mode

---

## 8. Estimated Effort

| Task | Effort |
|---|---|
| Line agent wrapper (Phase 1) | 2-3 hours |
| Tool-based approach (Phase 2, alternative) | 3-4 hours |
| Frontend integration (Phase 3) | 2-3 hours |
| Config toggle + dual WebSocket (Phase 4-5) | 1-2 hours |
| Testing + debugging | 2-3 hours |
| **Total** | **~8-12 hours** |

---

## 9. Decision: Wrapper vs Tool-Based

| Approach | Pros | Cons |
|---|---|---|
| **Wrapper** (Phase 1) | Reuses ALL existing agent logic. Minimal code changes. Safety pipeline stays identical. | Line's LLM is not used — we pipe transcript through our own Brain. Slightly less "native" Line integration. |
| **Tool-based** (Phase 2) | More idiomatic Line usage. Claude reasons about tools natively. Cleaner architecture long-term. | Requires re-implementing safety gates as tool guards. Risk analysis flow needs restructuring. More work. |

**Recommendation**: Start with the **Wrapper approach** (Phase 1). It's faster, safer,
and preserves all existing safety logic. Migrate to tool-based later if Line becomes
the primary voice backend.

---

## 10. References

- [Cartesia Line Platform](https://cartesia.ai/agents)
- [Line SDK GitHub](https://github.com/cartesia-ai/line)
- [Line Introduction Docs](https://docs.cartesia.ai/line/introduction)
- [Line Agents SDK Reference](https://docs.cartesia.ai/line/sdk/agents)
- [Line Web Calls Integration](https://docs.cartesia.ai/line/integrations/web-calls)
- [Line SDK Tips & Best Practices](https://docs.cartesia.ai/line/sdk/tips)
- [Quickstart: Talk to Your First Agent](https://docs.cartesia.ai/line/start-building/talk-to-your-first-agent)
- [Cartesia Sonic-3 TTS](https://cartesia.ai/sonic)
- [Cartesia Python SDK](https://github.com/cartesia-ai/cartesia-python)
- [Building Voice Agents Blog Post](https://cartesia.ai/blog/how-to-build-a-voice-ai-agent-with-cartesia)
- [Introducing Line Blog Post](https://cartesia.ai/blog/introducing-line-for-voice-agents)
