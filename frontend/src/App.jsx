import ActivityLog from './components/ActivityLog.jsx';
import BrowserView from './components/BrowserView.jsx';
import RiskBadge from './components/RiskBadge.jsx';
import VoicePanel from './components/VoicePanel.jsx';
import { useWebSocket } from './hooks/useWebSocket.js';

function getLatestUrl(events) {
  const browserEvent = [...events].reverse().find((event) => event.type === 'browser_update');
  return browserEvent?.url || 'about:blank';
}

function getLiveViewUrl(events) {
  const statusWithLiveView = [...events]
    .reverse()
    .find((event) => event.type === 'status' && event.metadata?.live_view_url);
  return statusWithLiveView?.metadata?.live_view_url || '';
}

export default function App() {
  const { connected, riskLevel, events, sendTranscript } = useWebSocket();

  return (
    <main className="layout">
      <h1>Accessibility Co-Pilot</h1>
      <p className="subtitle">Phase 0 scaffold: transcript in, safety-aware agent events out.</p>

      <div className="grid">
        <BrowserView currentUrl={getLatestUrl(events)} liveViewUrl={getLiveViewUrl(events)} />
        <div className="side-column">
          <VoicePanel connected={connected} onSend={sendTranscript} />
          <RiskBadge riskLevel={riskLevel} />
          <ActivityLog events={events} />
        </div>
      </div>
    </main>
  );
}
