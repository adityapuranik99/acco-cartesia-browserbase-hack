# Accessibility Co-Pilot

Phase 0/1 scaffold for a voice-first web safety agent.

## Run backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
python main.py
```

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` and send transcripts from the UI.

## Current status

- WebSocket backend (`/ws`) for transcript in -> agent events out
- Claude-based planner with typed `ActionPlan` schema and local fallback
- Browser controller adapter with Stagehand/Browserbase mode + stub mode fallback
- Browserbase Live View URL is emitted in status metadata and embedded in frontend iframe
- Multi-step action loop (up to 4 steps per turn) with inter-step safety checks
- Screenshot + DOM snapshot capture via Browserbase CDP for post-action risk analysis
- Optional Exa domain verification: official-domain lookup with mismatch override to `DANGER`
- Deterministic safety gate for risky flows (exact confirmation phrase required)
- Hardened payment submit policy with amount/payee readback confirmation phrase
- Cartesia TTS uses risk-based voice profiles (speed + emotion controls) from `SAFE` to `DANGER`
- Risk badge + activity log UI
- Fake scam page scaffold in `demo/fake-scam-site/`

## Runtime flags

- `ENABLE_CLAUDE=0|1`: opt-in live Claude planning (default `0` for deterministic fallback)
- `ENABLE_STAGEHAND=0|1`: opt-in live Browserbase/Stagehand automation (default `0`)
- `ENABLE_CARTESIA_TTS=0|1`: opt-in Cartesia audio generation on `agent_response` events
- `ENABLE_EXA_VERIFICATION=0|1`: enable Exa official-domain verification checks
- `CLAUDE_TIMEOUT_SEC` and `STAGEHAND_TIMEOUT_SEC`: fail-fast guardrails for demo stability

## Next steps

- Connect Cartesia Line for real audio I/O
- Add screenshot + DOM analysis pass for risk classification
- Add Exa/Notion integrations
