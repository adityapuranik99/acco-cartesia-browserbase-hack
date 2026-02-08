# Accessibility Co-Pilot

A voice-first web safety agent that helps visually impaired users navigate the web safely. The agent provides real-time risk assessment, natural voice guidance, and automated browser control with built-in scam detection.

## Overview

This system combines:
- **Voice Interface**: Cartesia-powered speech-to-text and text-to-speech with risk-adaptive voice profiles
- **AI Brain**: Claude-powered planning and multi-stage risk analysis (fast + deep)
- **Browser Automation**: Browserbase + Stagehand for live browser control with visual feedback
- **Safety Layer**: Multi-stage risk detection with domain verification, payment protection, and confirmation gates

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- API keys for Anthropic, Browserbase, and Cartesia

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Backend runs on `http://localhost:8000`

### 3. Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`

## Architecture

### Backend Components

- **Agent** ([agent.py](backend/agent.py)): Main orchestration loop with multi-step execution and safety gates
- **Brain** ([brain.py](backend/brain.py)): Claude-based planning and dual-stage risk analysis
- **Browser Controller** ([browser_controller.py](backend/browser_controller.py)): Browserbase/Stagehand adapter with fallback stub mode
- **Domain Verifier** ([domain_verifier.py](backend/domain_verifier.py)): Exa-powered official domain verification
- **Voice** ([voice.py](backend/voice.py)): Cartesia STT/TTS integration with risk-based voice profiles

### Frontend Components

- **VoicePanel**: Push-to-talk recording with Cartesia STT
- **ActivityLog**: Real-time event stream with risk badges
- **Live Browser View**: Embedded Browserbase session iframe
- **Risk Dashboard**: Visual risk level indicator

## Features

### Voice Interface
- Push-to-talk recording via Cartesia STT
- Natural, conversational TTS responses
- Risk-adaptive voice profiles:
  - SAFE: Normal, friendly tone
  - CAUTION: Slightly cautious
  - High Risk: Serious, clear warnings
  - DANGER: Urgent, protective

### Risk Analysis Pipeline

1. **Fast Risk Check** (Haiku, 2.2s timeout)
   - Immediate feedback on page load
   - Keyword-based fallback if timeout
   - Cost-optimized quick assessment

2. **Deep Risk Analysis** (Sonnet, parallel with action)
   - Screenshot + DOM analysis
   - Intent understanding
   - Detailed risk reasoning

3. **Domain Verification** (Exa)
   - Official domain lookup
   - Brand impersonation detection
   - Overrides risk to DANGER on mismatch

### Safety Gates

- **Confirmation Required**: Payment buttons and high-risk actions
- **Flexible Yes/No**: Natural language confirmation ("yes", "okay", "go ahead" vs "no", "stop", "cancel")
- **Payment Readback**: Amount and payee confirmation before submission
- **Action Blocking**: Automatic block on DANGER-level pages
- **Loop Detection**: Prevents infinite retry cycles

### Browser Control

- **Navigate**: Go to URLs with domain tracking
- **Act**: Click, type, scroll via Stagehand
- **Extract**: Read page content and answer questions
- **Multi-step**: Up to 4 actions per turn with inter-step safety checks
- **Progress Indicators**: Periodic updates during long operations

## Configuration

### Core Settings

```bash
# API Keys (required)
ANTHROPIC_API_KEY=sk-ant-...
BROWSERBASE_API_KEY=...
CARTESIA_API_KEY=...

# Enable/Disable Features
ENABLE_CLAUDE=1              # Live Claude planning (0 = deterministic fallback)
ENABLE_STAGEHAND=1           # Live browser automation (0 = stub mode)
ENABLE_CARTESIA_TTS=1        # Voice synthesis
ENABLE_CARTESIA_STT=1        # Voice input
ENABLE_EXA_VERIFICATION=1    # Domain verification
ENABLE_FAST_RISK_MODEL=1     # Fast Haiku risk checks
```

### Advanced Options

```bash
# Risk Analysis
FAST_RISK_MODEL_NAME=claude-3-5-haiku-20241022
FAST_RISK_TIMEOUT_SEC=2.2
CLAUDE_TIMEOUT_SEC=10

# Browser Automation
STAGEHAND_TIMEOUT_SEC=12
STAGEHAND_MODEL_NAME=anthropic/claude-sonnet-4-5

# Payment Safety
SAFE_PAYMENT_DOMAINS=pge.com,google.com

# Voice Profiles (optional risk-specific voices)
CARTESIA_VOICE_ID=f786b574-daa5-4673-aa0c-cbe3e8534c02
CARTESIA_VOICE_ID_CAUTION=...
CARTESIA_VOICE_ID_HIGH_RISK=...
CARTESIA_VOICE_ID_DANGER=...
```

## Usage Examples

### Basic Navigation
**User**: "Go to google.com"
- Agent navigates, analyzes risk, describes page
- **Risk**: SAFE

### Form Filling
**User**: "Log in to PG&E and pay my bill"
- Agent navigates, fills form, detects payment button
- **Risk**: High Risk → requests confirmation
- **Agent**: "Hey, I found a payment button. Want me to click it?"

### Scam Detection
**User**: "Go to urgent-account-suspended.com"
- Agent detects urgency in URL, suspicious language
- **Risk**: DANGER → blocks action
- **Agent**: "Whoa, hold on! This page looks suspicious. I think it might be a scam."

## Development

### Testing with Demo Scam Site

```bash
cd demo/fake-scam-site
python -m http.server 8080
# Visit http://localhost:8080
```

### Runtime Modes

**Development Mode** (safe testing):
```bash
ENABLE_CLAUDE=0
ENABLE_STAGEHAND=0
# Uses deterministic fallbacks, no real browser automation
```

**Live Mode** (requires API keys):
```bash
ENABLE_CLAUDE=1
ENABLE_STAGEHAND=1
ENABLE_CARTESIA_TTS=1
```

### WebSocket API

**Connect**: `ws://localhost:8000/ws`

**Send** (client → server):
```json
{"type": "transcript", "text": "go to google.com"}
```

**Receive** (server → client):
```json
{"type": "agent_response", "text": "Page loaded! What can I help you with?"}
{"type": "risk_update", "risk_level": "SAFE"}
{"type": "status", "text": "Navigation complete", "metadata": {...}}
{"type": "voice_state", "voice_state": "WORKING"}
```

## Project Structure

```
.
├── backend/
│   ├── agent.py              # Main agent orchestration
│   ├── brain.py              # Claude planning + risk analysis
│   ├── browser_controller.py # Browserbase/Stagehand wrapper
│   ├── domain_verifier.py    # Exa domain verification
│   ├── voice.py              # Cartesia STT/TTS
│   ├── models.py             # Pydantic data models
│   ├── config.py             # Environment configuration
│   └── main.py               # FastAPI server
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Main UI component
│   │   ├── components/
│   │   │   ├── VoicePanel.jsx    # Push-to-talk interface
│   │   │   └── ActivityLog.jsx   # Event stream display
│   │   └── hooks/
│   │       └── useWebSocket.js   # WebSocket connection
│   └── index.html
├── demo/
│   └── fake-scam-site/       # Test scam page for development
└── .env.example              # Configuration template
```

## Risk Levels

| Level | Description | Agent Behavior |
|-------|-------------|----------------|
| **SAFE** | Normal pages, no red flags | Proceeds automatically |
| **CAUTION** | Login forms, personal info | Proceeds with description |
| **High Risk** | Payment buttons, submissions | Requires explicit confirmation |
| **DANGER** | Scam indicators, domain mismatch | Blocks all actions, warns user |

## Contributing

This is a hackathon project. Key areas for improvement:
- [ ] Enhanced scam detection heuristics
- [ ] Multi-language voice support
- [ ] Session management and user preferences
- [ ] More robust error handling
- [ ] Performance optimizations

## License

MIT

## Acknowledgments

Built with:
- [Anthropic Claude](https://www.anthropic.com/) for AI planning and risk analysis
- [Browserbase](https://www.browserbase.com/) for cloud browser automation
- [Cartesia](https://www.cartesia.ai/) for real-time voice I/O
- [Stagehand](https://github.com/browserbase/stagehand) for browser control
- [Exa](https://exa.ai/) for domain verification
