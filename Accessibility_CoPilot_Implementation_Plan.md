# Accessibility Co-Pilot — Full Implementation Plan

**Hackathon:** Cartesia × Anthropic Voice Agents Hackathon hosted by Notion
**Date:** February 7–8, 2026 | Notion HQ, San Francisco
**Submission Deadline:** Sunday Feb 8, 12:00 PM
**Team Size:** Up to 4

---

## 1. What We're Building

**Accessibility Co-Pilot** is a voice-first agent that safely operates the web on behalf of users who are blind, elderly, or otherwise vulnerable. The user speaks a goal ("Pay my electricity bill"), and the agent navigates a real browser, detects risks (scams, accidental payments, dark patterns), and guides the user with expressive voice — adjusting tone, speed, and urgency based on what it sees on the page.

**This is not a screen reader. It is a guardian layer for the web.**

### One-Line Demo

> An elderly user attempts to pay an urgent "bill" on a fake website, and the agent slows down, warns them out loud, and blocks the payment until explicitly approved.

### Problem Statements Covered

| Statement | How We Hit It |
|---|---|
| **1. Expressive** | Cartesia Sonic emotion/speed controls map to risk levels — neutral for browsing, slow + serious for payments, urgent warnings for scams |
| **2. Advanced Reasoning** | Claude analyzes live page content, detects payment forms, urgency language, domain mismatches, and decides whether to proceed or intervene |
| **3. Situationally Aware** | Browserbase provides live web browsing; Exa verifies domains against real-world sources; the agent grounds every action in what it actually sees |
| **Notion Bonus Track** | Session logs written to a Notion database via MCP — caregiver audit trail |

---

## 2. Architecture

```
┌──────────────────────────────────────────────────┐
│              Web App (React / Next.js)            │
│                                                   │
│  ┌─────────────┐    ┌──────────────────────────┐ │
│  │ Voice Panel  │    │ Browserbase Embedded View │ │
│  │             │    │ (live cloud browser)      │ │
│  │ 🎙️ Mic In   │    │                           │ │
│  │ 🔊 Audio Out │    │ [user sees the real       │ │
│  │ ⚠️ Alerts   │    │  webpage being navigated] │ │
│  │ 📋 Log      │    │                           │ │
│  └─────────────┘    └──────────────────────────┘ │
└──────────────────────────────────────────────────┘
                        │
           ┌────────────┴────────────┐
           ▼                         ▼
┌─────────────────┐      ┌─────────────────────┐
│  Backend Agent   │      │  Browserbase API     │
│  (Python)        │      │  + Stagehand         │
│                  │◄────►│  (browser control)   │
│  - Cartesia Line │      └─────────────────────┘
│    (voice loop)  │
│  - Claude API    │      ┌─────────────────────┐
│    (reasoning)   │─────►│  Exa API             │
│  - Risk Engine   │      │  (domain verify,     │
│                  │      │   real-world search)  │
│                  │      └─────────────────────┘
│                  │
│                  │      ┌─────────────────────┐
│                  │─────►│  Notion MCP          │
│                  │      │  (audit log write)   │
└─────────────────┘      └─────────────────────┘
```

### UX Approach: Embedded Browser, Not Extension

We are NOT building a browser extension. Instead:

- Our web app embeds a Browserbase cloud browser session as the main viewport.
- The user interacts entirely through voice (and can watch the browser).
- Our app wraps the browser with a voice control panel, status indicators, and activity log.
- This is architecturally cleaner, more demo-friendly, and avoids all extension/injection complexity.

The user experience: open our app → speak your goal → watch the agent work → hear updates and warnings → confirm or stop.

---

## 3. Core Agent Loop

This is the central technical design. Every interaction follows this cycle:

```
1. USER SPEAKS GOAL
   └─► Cartesia Ink STT transcribes speech to text

2. INTENT PARSING
   └─► Claude receives transcript
   └─► Outputs: { goal, first_action, search_query? }

3. DOMAIN VERIFICATION (if navigating to a new site)
   └─► Exa searches for the legitimate domain
   └─► Claude compares target URL vs verified domain

4. BROWSER ACTION
   └─► Stagehand executes action on Browserbase session
       (navigate, click, type, scroll)
   └─► Returns: screenshot + DOM snapshot of resulting page

5. PAGE ANALYSIS & RISK DETECTION
   └─► Claude receives screenshot/DOM
   └─► Classifies page state:
       - SAFE: normal browsing, informational content
       - CAUTION: form detected, personal data fields
       - HIGH RISK: payment form, submission button, urgency language
       - DANGER: domain mismatch, scam indicators, dark patterns
   └─► Decides: proceed / narrate / warn / block-and-confirm

6. VOICE RESPONSE
   └─► Cartesia Sonic TTS speaks to user
   └─► Voice parameters adapt to risk level:
       - SAFE: normal speed, neutral emotion
       - CAUTION: slightly slower, attentive tone
       - HIGH RISK: slow, deliberate, serious tone
       - DANGER: slow, firm, concerned tone + explicit warning

7. IF CONFIRMATION NEEDED
   └─► Agent asks for explicit verbal confirmation
   └─► Waits for user to say "yes" / "confirm" / "stop"
   └─► Only proceeds on clear affirmative

8. LOG ACTION
   └─► Write to Notion database: timestamp, action, risk level, outcome

9. LOOP back to step 4 until goal is complete or user stops
```

---

## 4. Technology Stack & API Keys

| Component | Technology | Purpose |
|---|---|---|
| **Voice In** | Cartesia Ink (STT) via Line SDK | Transcribe user speech |
| **Voice Out** | Cartesia Sonic 3 (TTS) via Line SDK | Speak to user with emotion/speed control |
| **Voice Orchestration** | Cartesia Line SDK (Python) | Manage audio pipeline, turn-taking, interruptions |
| **Reasoning** | Claude API (Sonnet 4.5 or Opus 4.6) | Intent parsing, page analysis, risk detection, action planning |
| **Browser** | Browserbase + Stagehand | Cloud browser sessions, page interaction |
| **Web Search** | Exa API | Domain verification, real-world grounding |
| **Audit Log** | Notion MCP | Write session logs for caregiver review |
| **Frontend** | React / Next.js | UI shell with embedded browser + voice panel |

### API Keys & Credits

- **Cartesia:** Account at cartesia.ai (hackathon credits provided)
- **Anthropic Claude:** $25 credits via hackathon form
- **Browserbase:** Code `STARTERPACK` for 3 months free Developer Plan
- **Exa:** Code `EXTACARTESIAHACKATHON` for $50 free credits at dashboard.exa.ai/billing
- **Notion:** Account at notion.com; workspace upgrade requested by Feb 5

---

## 5. Risk Detection — Claude Prompt Design

The core risk detection is a Claude prompt that receives page state and classifies it. Keep this focused on a few high-signal checks rather than trying to catch everything.

### Signals to Detect (Scoped for Hackathon)

1. **Domain Mismatch**
   - Use Exa to search for the real domain of the service (e.g., "PG&E official website")
   - Compare against the current URL
   - Flag if domains don't match

2. **Payment Page Detection**
   - Look for payment form elements: credit card fields, "Pay Now" buttons, dollar amounts
   - Flag any page requesting financial information

3. **Urgency / Scare Tactics**
   - Detect language patterns: "Act now", "Your account will be suspended", "Immediate payment required", countdown timers
   - These are classic scam indicators

4. **Confirmation Gate**
   - ANY payment or form submission requires explicit verbal "yes"
   - On DANGER pages, require the user to say a specific confirmation phrase

### Example Claude System Prompt for Page Analysis

```
You are a web safety analyzer for elderly and blind users. You receive a 
screenshot and/or DOM content of a webpage the user is currently viewing.

Classify the page into one of these risk levels:
- SAFE: Informational content, navigation, search results
- CAUTION: Forms requesting personal information, account pages
- HIGH_RISK: Payment forms, checkout pages, subscription signups
- DANGER: Domain doesn't match expected service, urgency/scare language, 
  suspicious payment requests, known scam patterns

For each classification, output:
{
  "risk_level": "SAFE|CAUTION|HIGH_RISK|DANGER",
  "risk_reasons": ["list of specific concerns"],
  "recommended_action": "proceed|narrate|warn|block",
  "voice_message": "what to say to the user",
  "voice_emotion": "neutral|attentive|serious|concerned",
  "voice_speed": "normal|slow|very_slow",
  "requires_confirmation": true/false,
  "next_browser_action": { "type": "click|type|navigate|wait", ... }
}
```

---

## 6. Voice Design — Cartesia Sonic Configuration

The voice is not cosmetic. It is the primary safety interface.

### Voice Parameter Mapping

| Risk Level | Speed | Emotion | Behavior |
|---|---|---|---|
| **SAFE** | `normal` | `neutral` | Brief status updates: "I'm on the PG&E homepage. Looking for the bill pay section." |
| **CAUTION** | `slow` | `attentive` / `content` | "This page is asking for your account number. I'll read back what I enter before submitting." |
| **HIGH_RISK** | `slow` | `serious` | "I've found a payment page. The amount is $142.50. Before I proceed, please confirm you'd like to pay this amount." |
| **DANGER** | `very_slow` | `concerned` / `serious` | "Hold on. This doesn't look right. The website address doesn't match PG&E's official site. I'm seeing urgent language designed to pressure you. I recommend not entering any information here." |

### Recommended Voice IDs (for voice agents)

- Primary: **Katie** (`f786b574-daa5-4673-aa0c-cbe3e8534c02`) — stable, realistic, good for agents
- Alternative: **Kiefer** (`228fca29-3a0a-435c-8728-5cb83251068`) — male voice option
- For expressive warnings: **Tessa** (`6ccbfb76-1fc6-48f7-b71d-91ac6298247b`) — tagged as emotive

### Cartesia Line SDK Voice Agent Skeleton

```python
from line import Agent, Context

class AccessibilityCoPilot(Agent):
    async def on_message(self, ctx: Context, text: str):
        # 1. Parse intent with Claude
        intent = await self.parse_intent(text)
        
        # 2. Execute browser action
        page_state = await self.browser_action(intent)
        
        # 3. Analyze risk
        risk = await self.analyze_risk(page_state)
        
        # 4. Respond with appropriate voice
        await ctx.say(
            risk["voice_message"],
            speed=risk["voice_speed"],
            emotion=risk["voice_emotion"]
        )
        
        # 5. If confirmation needed, wait
        if risk["requires_confirmation"]:
            await ctx.say(
                "Please say 'yes' to proceed or 'stop' to cancel.",
                speed="very_slow",
                emotion="serious"
            )
```

---

## 7. Notion Integration (Bonus Track)

Minimal but valuable. One Notion database, one write per significant action.

### Database Schema

| Property | Type | Example |
|---|---|---|
| Session ID | Title | `session_2026-02-08_001` |
| Timestamp | Date | `2026-02-08T10:32:00` |
| User Goal | Rich Text | "Pay electricity bill" |
| Sites Visited | Multi-select | `pge.com`, `pge-billing-urgent.com` |
| Actions Taken | Rich Text | "Navigated to PG&E, detected scam redirect, blocked payment" |
| Risk Events | Rich Text | "DANGER: Domain mismatch detected on pge-billing-urgent.com" |
| Outcome | Select | `Blocked` / `Completed` / `User Cancelled` |
| Warnings Issued | Number | `2` |

### Integration via Notion MCP

```python
# Using Notion MCP server or direct API
async def log_to_notion(session_data):
    # Write a new page to the audit database
    await notion_client.pages.create(
        parent={"database_id": AUDIT_DB_ID},
        properties={
            "Session ID": {"title": [{"text": {"content": session_data["id"]}}]},
            "User Goal": {"rich_text": [{"text": {"content": session_data["goal"]}}]},
            "Outcome": {"select": {"name": session_data["outcome"]}},
            "Warnings Issued": {"number": session_data["warning_count"]},
            # ...
        }
    )
```

The caregiver opens Notion and sees a clean database of every session — what the user tried to do, what risks were detected, and what happened. This is the "peace of mind" feature.

---

## 8. Demo Script (3 Minutes)

This is what we show judges. One continuous flow, no slides.

### Setup

- App is open with embedded Browserbase browser and voice panel visible.
- A fake scam site is pre-deployed (e.g., `pge-billing-urgent.example.com`) that mimics PG&E with urgency language and a payment form.

### Flow

**[0:00–0:20] Introduction**
- Briefly explain: "Accessibility Co-Pilot is a voice agent that helps blind and elderly users navigate the web safely."
- "Let me show you what happens when my grandmother tries to pay her electric bill."

**[0:20–0:50] Happy Path Start**
- User says: *"I need to pay my electric bill."*
- Agent (warm, normal speed): *"I'll help you with that. Let me navigate to PG&E's website."*
- Browser navigates to real PG&E site. Agent narrates: *"I'm on PG&E's homepage. I can see a 'Pay Bill' button. Let me click that."*

**[0:50–1:30] Scam Redirect**
- Simulate: clicking a link redirects to the fake scam site.
- Agent's tone shifts immediately — slower, more serious: *"Hold on. Something changed. The website address is now pge-billing-urgent dot com. This does not match PG&E's official website."*
- Agent continues: *"I'm also seeing language that says 'Your service will be terminated in 24 hours.' This is a pressure tactic commonly used in scams."*
- Agent: *"I strongly recommend not entering any payment information on this page."*

**[1:30–2:00] User Pushes Back**
- User says: *"But I need to pay my bill!"*
- Agent (empathetic but firm): *"I understand. Let me take you to PG&E's real website so you can pay safely."*
- Browser navigates to the real site. Agent: *"We're now on PGE dot com, the verified official site. I can see your account login. Would you like me to proceed?"*

**[2:00–2:30] Safe Payment with Confirmation**
- Agent finds the payment page on the real site.
- Agent (slow, deliberate): *"I've found your bill. The amount due is one hundred forty-two dollars and fifty cents. To confirm this payment, please say 'yes, pay.'*"
- User: *"Yes, pay."*
- Agent: *"Payment confirmed. I've logged this session for your records."*

**[2:30–3:00] Show Notion Log + Wrap Up**
- Briefly switch to Notion — show the audit log entry with the scam warning, the redirect, and the final safe completion.
- Close: "Accessibility Co-Pilot doesn't just read the web. It protects you from it."

---

## 9. Implementation Phases — Build Order

### Critical Path Refinements (Recommended Before Coding)

1. **Move one hard safety gate to Phase 0**
   - Implement a deterministic rule immediately: never submit any form or payment action without explicit verbal confirmation.
   - This must be enforced in code even if Claude fails, times out, or misclassifies risk.

2. **Use a strict action schema for all agent browser actions**
   - Do not execute free-form action text directly.
   - Parse model output into a validated action contract:
     - `navigate(url)`
     - `act(instruction)`
     - `extract(instruction)`
     - `confirm(action_id, confirmation_phrase)`
     - `stop(reason)`

3. **Build with a fallback mode from day one**
   - Primary demo path: Cartesia + Browserbase + Claude.
   - Fallback demo path: deterministic scripted flow if Claude/Exa latency spikes.
   - UI should expose when fallback mode is active so judges understand behavior.

4. **Tighten payment confirmation semantics**
   - For payments, require an amount-bound phrase (example: `"yes, pay 142 dollars and 50 cents"`).
   - On mismatch, block and re-read amount before retrying.

### PHASE 0: Skeleton (First 2 Hours) — GET SOMETHING TALKING

**Goal: A voice agent that can speak, listen, and control a browser. No intelligence yet.**

Backend:
- [ ] Set up project repo (Python backend, React frontend)
- [ ] Get Cartesia Line SDK running with a `ReasoningNode` subclass that echoes what you say
- [ ] Create Browserbase session using `AsyncStagehand`
- [ ] Verify Stagehand can navigate to a URL using natural language: `await session.act(input="Navigate to google.com")`
- [ ] Set up WebSocket connection between backend (agent) and frontend for real-time events
- [ ] Add deterministic safety middleware: block submit/payment actions unless `confirmation_state == confirmed`

Frontend:
- [ ] Create React app with basic layout
- [ ] Embed Browserbase session using iframe or Browserbase live view API
- [ ] Add microphone button + audio output (connect to Cartesia via WebSocket)
- [ ] Display agent status updates (e.g., "Navigating...", "Analyzing page...")

Integration:
- [ ] Wire end-to-end: user clicks mic → speaks "Go to Google" → backend echoes "Going to Google" → browser navigates → frontend shows browser + plays voice

**Milestone: You speak, the agent speaks back, the browser moves. End to end.**

**Key Pattern from Example:** Use `asyncio.create_task()` for browser actions so voice continues without blocking:
```python
# Don't await browser actions in main loop
asyncio.create_task(self.navigate_to(url))
yield AgentResponse(content="Navigating now...")
```

---

### PHASE 1: Claude Brain (Next 3 Hours)

**Goal: Claude interprets intent and analyzes pages.**

- [ ] Connect Claude API to the agent loop (use `anthropic.Anthropic()` client)
- [ ] Intent parsing: Define Claude tool for structured output (JSON Schema object with typed fields)
  ```python
  tools = [{
      "name": "navigate_to_site",
      "input_schema": {
          "service_name": "string",  # e.g., "PG&E"
          "url": "string",
          "reason": "string"
      }
  }]
  ```
- [ ] Page analysis: After browser navigation, capture screenshot + DOM:
  ```python
  # Stagehand provides screenshot capability
  screenshot = await session.page.screenshot()
  dom_snapshot = await session.page.content()

  # Send both to Claude vision API
  response = claude.messages.create(
      model="claude-sonnet-4-5-20250929",
      messages=[{
          "role": "user",
          "content": [
              {"type": "image", "source": {"type": "base64", "data": screenshot_b64}},
              {"type": "text", "text": f"DOM: {dom_snapshot}\n\nAnalyze this page..."}
          ]
      }]
  )
  ```
- [ ] Use Stagehand's `extract()` method to pull specific info: `await session.extract(instruction="What is the page title?")`
- [ ] Wire full flow: "Pay my electric bill" → Claude tool call `navigate_to_site(service="PG&E")` → Stagehand navigates → Screenshot analysis → Narrate findings
- [ ] Validate every Claude action against your internal action schema before execution

**Milestone: The agent understands goals and can describe what it sees on a page.**

**Key Pattern from Example:** Maintain conversation history in `ConversationContext`, plus a separate structured state object (`current_goal`, `expected_service`, `pending_confirmation`, `last_risk_level`) for deterministic safety checks.

---

### PHASE 2: Risk Detection (Next 3 Hours)

**Goal: The agent detects danger and changes behavior.**

- [ ] Implement the risk classification prompt (SAFE / CAUTION / HIGH_RISK / DANGER)
  - Create `risk_prompts.py` with Claude system prompt template
  - Define structured output schema using Claude tool calling:
  ```python
  risk_tool = {
      "name": "report_risk_level",
      "input_schema": {
          "risk_level": {"enum": ["SAFE", "CAUTION", "HIGH_RISK", "DANGER"]},
          "risk_reasons": {"type": "array"},
          "voice_message": "string",
          "voice_speed": {"enum": ["normal", "slow", "very_slow"]},
          "voice_emotion": {"enum": ["neutral", "attentive", "serious", "concerned"]},
          "requires_confirmation": "boolean"
      }
  }
  ```
- [ ] Map risk levels to Cartesia voice parameters (speed, emotion)
  ```python
  # In your ReasoningNode's process_context:
  yield AgentResponse(
      content=risk["voice_message"],
      speed=risk["voice_speed"],       # Line SDK parameter
      emotion=risk["voice_emotion"]    # Line SDK parameter
  )
  ```
- [ ] Build the confirmation gate: HIGH_RISK and DANGER pages require verbal "yes"
  - Wait for user's next transcript
  - Check if it matches confirmation phrases ("yes", "confirm", "proceed")
  - If not confirmed, block action and redirect
- [ ] Integrate Exa for domain verification (run in background task):
  ```python
  async def verify_domain_async(self, service_name: str, current_url: str):
      results = await exa.search(f"{service_name} official website")
      verified_domain = extract_domain(results[0].url)
      current_domain = extract_domain(current_url)
      return verified_domain == current_domain
  ```
- [ ] Deploy the fake scam site for demo purposes
  - Create `demo/fake-scam-site/index.html` with urgency language, countdown timer, payment form
  - Host on Vercel/Netlify with domain like `pge-billing-urgent.vercel.app`
  - Add visible scam indicators: domain mismatch, "Act now!", fake urgency

**Milestone: The agent's voice changes when it encounters a risky page and blocks payments on suspicious sites.**

**Key Pattern from Example:** Use background tasks for Exa lookups and screenshot analysis to prevent voice lag:
```python
# Start verification in background
verification_task = asyncio.create_task(self.verify_domain_async(service, url))

# Continue speaking while it runs
yield AgentResponse(content="Let me verify this is the right website...")

# Await only when you need the result
is_verified = await verification_task
```

---

### PHASE 3: Demo Polish (Next 2–3 Hours)

**Goal: The demo flows perfectly end-to-end.**

- [ ] Script the exact demo flow and test it repeatedly
- [ ] Tune voice messages — make them concise, clear, natural
- [ ] Handle the "user pushes back" interaction (empathetic redirection)
- [ ] Add visual indicators to the UI (risk level badge, status text)
- [ ] Handle edge cases: what if Claude is slow? (add "Let me check this page..." filler speech)

**Milestone: The full demo runs smoothly in under 3 minutes.**

---

### PHASE 4: Notion + Extras (Last 1–2 Hours, If Time Permits)

**Goal: Bonus track eligibility and polish.**

- [ ] Set up Notion database for audit logs
- [ ] Write session summary to Notion after each completed/blocked session
- [ ] Add a "Caregiver View" panel or link in the UI that opens the Notion log
- [ ] Record the 1-minute submission video
- [ ] Clean up repo, add README, ensure everything is open source

**Milestone: Notion log works, video recorded, submission ready.**

---

## 10. File Structure (Revised with Example Patterns)

```
accessibility-copilot/
├── README.md
├── LICENSE                    # Open source license (required by rules)
├── backend/
│   ├── main.py                # Entry point - WebSocket server + voice agent coordinator
│   ├── agent.py               # AccessibilityCopilot class (extends ReasoningNode)
│   ├── brain.py               # Claude API integration (intent + risk)
│   │                          # - parse_intent(transcript) -> Intent
│   │                          # - analyze_page(screenshot, dom) -> RiskAssessment
│   ├── browser_controller.py # Browserbase + Stagehand wrapper
│   │                          # - AsyncStagehand session management
│   │                          # - navigate(url), extract(instruction), screenshot()
│   ├── domain_verifier.py     # Exa integration for domain checking
│   ├── notion_logger.py       # Notion MCP audit logging (optional - Phase 4)
│   ├── risk_prompts.py        # Claude system prompts for risk classification
│   ├── config.py              # API keys, voice IDs, Cartesia settings
│   ├── models.py              # Pydantic models (Intent, RiskAssessment, etc.)
│   └── requirements.txt       # cartesia-line, stagehand, anthropic, exa-py, etc.
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── App.jsx            # Main layout with grid: browser left, controls right
│   │   ├── components/
│   │   │   ├── BrowserView.jsx      # Browserbase session iframe/live view
│   │   │   ├── VoicePanel.jsx       # Mic button, audio waveform, status
│   │   │   ├── RiskBadge.jsx        # Large color-coded risk indicator
│   │   │   ├── ActivityLog.jsx      # Scrolling log of actions/events
│   │   │   └── TranscriptDisplay.jsx # Real-time transcript of conversation
│   │   ├── hooks/
│   │   │   └── useWebSocket.js      # WebSocket connection to backend
│   │   └── utils/
│   │       └── audioUtils.js        # Web Audio API for Cartesia integration
│   ├── package.json
│   └── vite.config.js
├── demo/
│   ├── fake-scam-site/
│   │   ├── index.html           # Scam page with urgency language
│   │   ├── styles.css           # Make it look "real" but sketchy
│   │   └── README.md            # How to deploy to Vercel
│   ├── demo-script.md           # Exact flow for 3-minute demo
│   └── test-scenarios.md        # Test cases for development
├── .env.example               # Template for all API keys
├── .gitignore
└── cartesia.toml              # Cartesia deployment config (if deploying to their platform)
```

**Key Architecture Decisions from Example:**

1. **agent.py extends ReasoningNode**: Follows the Line SDK pattern for voice agents
2. **Async everywhere**: All I/O operations (browser, Claude, Exa) use `asyncio.create_task()` to prevent blocking
3. **WebSocket bridge**: Backend sends events to frontend (risk updates, navigation events, transcript)
4. **Natural language browser control**: Use Stagehand's `act(input="...")` and `extract(instruction="...")` instead of Playwright selectors
5. **Tool-calling for structured output**: Claude returns JSON via tool calls, not raw text parsing

---

## 11. Key Integration Patterns (From Browserbase Example)

### Pattern 1: ReasoningNode Architecture

Your agent should extend Cartesia Line's `ReasoningNode` class:

```python
from line.nodes.reasoning import ReasoningNode
from line.events import AgentResponse
from line.nodes.conversation_context import ConversationContext

class AccessibilityCopilot(ReasoningNode):
    def __init__(self, system_prompt: str, max_context_length: int = 15):
        super().__init__(system_prompt=system_prompt, max_context_length=max_context_length)
        self.browserbase_session = None
        self.risk_detector = RiskDetector()
        self.collected_data = {}

    async def process_context(self, context: ConversationContext):
        """Called every time user speaks. Yield AgentResponse objects to reply."""

        # Get what user said
        user_message = context.get_latest_user_transcript_message()

        # Your logic here...
        yield AgentResponse(content="I heard you, let me help with that...")
```

### Pattern 2: Non-Blocking Browser Automation

**Critical:** Don't await browser actions in the main conversation flow. Use background tasks:

```python
async def process_context(self, context: ConversationContext):
    user_said = context.get_latest_user_transcript_message()

    # Parse intent
    intent = await self.parse_intent(user_said)

    # Start browser navigation in background (don't await!)
    navigation_task = asyncio.create_task(self.navigate_and_analyze(intent["url"]))

    # Continue speaking immediately
    yield AgentResponse(
        content=f"I'm navigating to {intent['service']} now. One moment...",
        speed="normal",
        emotion="neutral"
    )

    # Later, when you need the result:
    page_state = await navigation_task

    # Analyze and respond
    risk = await self.detect_risk(page_state)
    yield AgentResponse(
        content=risk["voice_message"],
        speed=risk["voice_speed"],
        emotion=risk["voice_emotion"]
    )
```

### Pattern 3: Stagehand Natural Language API

Use natural language instructions instead of CSS selectors:

```python
from stagehand import AsyncStagehand

# Initialize
self.stagehand = AsyncStagehand(
    browserbase_api_key=os.getenv("BROWSERBASE_API_KEY"),
    browserbase_project_id=os.getenv("BROWSERBASE_PROJECT_ID"),
    model_api_key=os.getenv("ANTHROPIC_API_KEY")  # Stagehand can use Claude!
)

session = await self.stagehand.sessions.create(model_name="claude-sonnet-4-5")

# Navigation
await session.navigate(url="https://pge.com")

# Actions (natural language!)
await session.act(input="Click the 'Pay My Bill' button")
await session.act(input="Enter '123456789' in the account number field")

# Information extraction
amount = await session.extract(instruction="What is the total amount due?")
page_title = await session.extract(instruction="What is the page title?")

# Screenshots
screenshot = await session.page.screenshot()  # Returns bytes
```

### Pattern 4: Claude Tool Calling for Structured Output

Define tools for Claude to return structured data:

```python
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

tools = [
    {
        "name": "report_risk_assessment",
        "description": "Report the safety risk level of the current webpage",
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_level": {
                    "type": "string",
                    "enum": ["SAFE", "CAUTION", "HIGH_RISK", "DANGER"],
                    "description": "The risk level classification"
                },
                "risk_reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of specific concerns"
                },
                "voice_message": {
                    "type": "string",
                    "description": "What to say to the user"
                },
                "voice_speed": {
                    "type": "string",
                    "enum": ["normal", "slow", "very_slow"]
                },
                "voice_emotion": {
                    "type": "string",
                    "enum": ["neutral", "attentive", "serious", "concerned"]
                },
                "requires_confirmation": {
                    "type": "boolean",
                    "description": "Whether user must verbally confirm before proceeding"
                }
            },
            "required": ["risk_level", "voice_message", "voice_speed", "voice_emotion"]
        }
    }
]

response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=1024,
    tools=tools,
    messages=[{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}},
            {"type": "text", "text": f"Analyze this page for safety risks...\n\nDOM: {dom_content}"}
        ]
    }]
)

# Extract tool call
if response.stop_reason == "tool_use":
    tool_use = next(block for block in response.content if block.type == "tool_use")
    risk_assessment = tool_use.input  # This is your structured data!
```

### Pattern 5: WebSocket Bridge to Frontend

Connect your React frontend to the Python backend:

```python
# backend/main.py
import asyncio
from fastapi import FastAPI, WebSocket
from agent import AccessibilityCopilot

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Create agent instance
    copilot = AccessibilityCopilot()

    # Listen for user audio/commands
    async for message in websocket.iter_json():
        if message["type"] == "user_speech":
            # Process with agent
            responses = copilot.process_user_input(message["transcript"])

            async for response in responses:
                # Send back to frontend
                await websocket.send_json({
                    "type": "agent_response",
                    "text": response.content,
                    "audio": response.audio_data,  # Cartesia TTS output
                    "metadata": {
                        "speed": response.speed,
                        "emotion": response.emotion
                    }
                })

        elif message["type"] == "browser_event":
            # Send browser updates to frontend
            await websocket.send_json({
                "type": "browser_update",
                "url": copilot.current_url,
                "screenshot": base64_screenshot
            })
```

```javascript
// frontend/src/hooks/useWebSocket.js
import { useEffect, useState } from 'react';

export function useWebSocket() {
  const [ws, setWs] = useState(null);
  const [agentStatus, setAgentStatus] = useState('idle');
  const [transcript, setTranscript] = useState([]);

  useEffect(() => {
    const websocket = new WebSocket('ws://localhost:8000/ws');

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'agent_response') {
        setTranscript(prev => [...prev, { speaker: 'agent', text: data.text }]);
        // Play audio
        playAudio(data.audio);
      }

      if (data.type === 'risk_update') {
        setAgentStatus(data.risk_level);
      }
    };

    setWs(websocket);
    return () => websocket.close();
  }, []);

  const sendSpeech = (transcript) => {
    ws.send(JSON.stringify({ type: 'user_speech', transcript }));
  };

  return { sendSpeech, agentStatus, transcript };
}
```

### Pattern 6: Voice Parameter Control

Map risk levels directly to Cartesia voice parameters:

```python
VOICE_PARAMS = {
    "SAFE": {
        "speed": "normal",
        "emotion": "neutral",
    },
    "CAUTION": {
        "speed": "slow",
        "emotion": "attentive",
    },
    "HIGH_RISK": {
        "speed": "slow",
        "emotion": "serious",
    },
    "DANGER": {
        "speed": "very_slow",
        "emotion": "concerned",
    }
}

# In your agent:
risk_level = risk_assessment["risk_level"]
params = VOICE_PARAMS[risk_level]

yield AgentResponse(
    content=risk_assessment["voice_message"],
    speed=params["speed"],
    emotion=params["emotion"]
)
```

---

## 12. Key Technical Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Claude latency (2–3s per reasoning step)** | Awkward silence during page analysis | Have the agent say "Let me check this page..." as filler while Claude thinks. Use streaming responses. Use background tasks (`asyncio.create_task()`) so voice continues. |
| **Browserbase session instability** | Demo crashes mid-presentation | Pre-test demo sites extensively. Have a screen recording as backup. Keep sessions short. Store session ID in case you need to reconnect. |
| **Stagehand failing on complex sites** | Can't navigate real PG&E | For the demo, use a simplified mock site that looks realistic but is guaranteed to work. Real PG&E can be a stretch goal. The example template uses natural language actions - this is more reliable than Playwright selectors. |
| **Voice turn-taking issues** | Agent talks over user or vice versa | Cartesia Line SDK handles this via Bridge pattern with interrupts. Test interruption behavior early: `form_bridge.on(UserStoppedSpeaking).interrupt_on(UserStartedSpeaking)` |
| **Scope creep** | Try to build too many features | Stick to ONE demo flow. The scam detection scenario is the whole demo. |
| **Frontend-Backend sync issues** | Browser state out of sync with voice | Use WebSocket events to broadcast all state changes. Send `browser_update` events whenever navigation happens. |
| **Audio handling complexity** | Cartesia audio not playing in browser | Use Web Audio API or `<audio>` elements. Cartesia Line SDK can output PCM audio that you stream to frontend. Consider using their phone integration first, add web audio later. |

---

## 13. Judging Criteria Alignment

| Criteria | Weight | Our Angle |
|---|---|---|
| **Demo** | 50% | Live voice agent navigates a real browser, catches a scam, protects the user. Emotionally powerful moment when tone shifts. |
| **Impact** | 25% | Addresses a genuine safety gap for millions of elderly and blind users. Scam losses exceed $10B/year in the US alone. |
| **Creativity** | 15% | Voice as a safety primitive (not just TTS). Embedded browser approach. Risk-adaptive expressiveness. |
| **Pitch** | 10% | Lead with the grandmother story. Close with "this is not a chatbot with a voice — it's a guardian layer." |

---

## 14. Anti-Patterns to Avoid

Per hackathon rules, DO NOT:

- ❌ Build a "basic RAG application"
- ❌ Build a "medical advice" tool
- ❌ Build an "AI companion chatbot"
- ❌ Use Streamlit
- ❌ Show slides during judging (they want technical demos only)
- ❌ Ship unmodified boilerplate without adapting it to your unique risk-guardrail behavior

We're safe on all of these. This is a novel agent with real browser control, not a chatbot.

---

## 15. Quick Reference — API Snippets

### Cartesia Sonic TTS (direct, for testing)

```python
from cartesia import Cartesia

client = Cartesia(api_key=os.getenv("CARTESIA_API_KEY"))

# Generate warning speech
audio = client.tts.bytes(
    model_id="sonic-3",
    transcript="Hold on. This website doesn't look right.",
    voice={"mode": "id", "id": "f786b574-daa5-4673-aa0c-cbe3e8534c02"},
    language="en",
    output_format={"container": "wav", "sample_rate": 44100, "encoding": "pcm_f32le"},
)
```

### Claude Page Analysis (direct, for testing)

```python
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}},
            {"type": "text", "text": "Analyze this webpage for safety risks. Classify as SAFE/CAUTION/HIGH_RISK/DANGER..."}
        ]
    }]
)
```

### Exa Domain Verification

```python
from exa_py import Exa

exa = Exa(os.getenv("EXA_API_KEY"))

results = exa.search(
    "PG&E official website for paying electricity bills",
    num_results=3,
    type="neural"
)
# Compare results[0].url domain against current browser URL
```

### Browserbase + Stagehand

```python
# Create a session
from browserbase import Browserbase

bb = Browserbase(api_key=os.getenv("BROWSERBASE_API_KEY"))
session = bb.sessions.create(project_id=os.getenv("BROWSERBASE_PROJECT_ID"))

# Use Stagehand for AI-powered browser actions
# stagehand.act("Click the Pay Bill button")
# stagehand.extract("What is the total amount due?")
```

### Notion Audit Log

```python
from notion_client import Client

notion = Client(auth=os.getenv("NOTION_API_KEY"))

notion.pages.create(
    parent={"database_id": AUDIT_DB_ID},
    properties={
        "Session ID": {"title": [{"text": {"content": session_id}}]},
        "User Goal": {"rich_text": [{"text": {"content": "Pay electricity bill"}}]},
        "Risk Events": {"rich_text": [{"text": {"content": "DANGER: Domain mismatch on pge-billing-urgent.com"}}]},
        "Outcome": {"select": {"name": "Blocked — redirected to real site"}},
    }
)
```

---

## 16. Web Frontend Voice Integration (Beyond the Example)

The example uses phone calls, but we want web-based voice. Here are two approaches:

### Approach A: Cartesia Line with Custom Audio Bridge (Recommended)

Use Cartesia Line SDK on backend, stream audio to/from frontend:

```python
# backend/main.py
from line import VoiceAgentApp, Bridge
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/voice")
async def voice_websocket(websocket: WebSocket):
    await websocket.accept()

    # Create Line agent
    copilot = AccessibilityCopilot()

    # Stream audio chunks bidirectionally
    async def send_audio_to_agent():
        async for message in websocket.iter_bytes():
            # message is PCM audio from frontend microphone
            await copilot.receive_audio(message)

    async def send_audio_to_frontend():
        async for audio_chunk in copilot.audio_output_stream():
            # Send Cartesia TTS audio to frontend
            await websocket.send_bytes(audio_chunk)

    await asyncio.gather(send_audio_to_agent(), send_audio_to_frontend())
```

```javascript
// frontend/src/hooks/useCartesiaVoice.js
export function useCartesiaVoice() {
  const [isRecording, setIsRecording] = useState(false);
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);

  const startRecording = async () => {
    // Connect WebSocket
    wsRef.current = new WebSocket('ws://localhost:8000/voice');

    // Capture microphone
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioContext = new AudioContext({ sampleRate: 16000 });
    audioContextRef.current = audioContext;

    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (e) => {
      // Send PCM audio to backend
      const audioData = e.inputBuffer.getChannelData(0);
      const pcm16 = float32ToPCM16(audioData);
      wsRef.current.send(pcm16);
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    // Play incoming audio
    wsRef.current.onmessage = (event) => {
      const audioData = new Uint8Array(event.data);
      playAudioChunk(audioData, audioContext);
    };

    setIsRecording(true);
  };

  return { startRecording, isRecording };
}
```

### Approach B: Use Cartesia Phone + Screen Share (Simpler for Demo)

Keep the example's phone-based approach, add web UI just for visualization:

1. User opens your web app
2. Web app displays: "Call this number to start: +1-XXX-XXX-XXXX"
3. User calls the number on their phone
4. Web app shows the Browserbase session + transcript + risk indicators
5. Voice interaction happens entirely over phone

**Pros:** No need to build web audio infrastructure, Line SDK works as-is
**Cons:** User needs to use phone, which is actually realistic for your accessibility use case!

### Recommendation for Hackathon

**Start with Approach B (phone + web visualization).** This gets you to a working demo faster. The web UI focuses on what judges can *see* (browser automation, risk detection, visual indicators), while voice happens naturally over phone.

If time permits, upgrade to Approach A for the "wow factor" of in-browser voice.

---

## 17. Quick Start Commands

Once you start building, here's how to run everything:

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
cp .env.example .env  # Fill in your API keys
python main.py  # Starts voice agent + WebSocket server

# Frontend (separate terminal)
cd frontend
npm install
npm run dev  # Starts React app on localhost:5173

# Fake scam site (separate terminal)
cd demo/fake-scam-site
npx vercel dev  # Or use `python -m http.server 3000`
```

### Essential Environment Variables

```bash
# .env
CARTESIA_API_KEY=your_cartesia_key
ANTHROPIC_API_KEY=your_claude_key
BROWSERBASE_API_KEY=your_browserbase_key
BROWSERBASE_PROJECT_ID=your_project_id
EXA_API_KEY=your_exa_key
NOTION_API_KEY=your_notion_key  # Optional - Phase 4
```

---

*This document is the single source of truth for building Accessibility Co-Pilot at the hackathon. Feed it to Claude Code and start with Phase 0.*
