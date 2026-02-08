import { useEffect, useState } from 'react';
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
  const { connected, riskLevel, voiceState, events, sendTranscript, sendInterrupt } = useWebSocket();
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <div className="brand-icon">
              <span className="material-icons-outlined">assist_walker</span>
            </div>
            <div>
              <h1 className="brand-title">Accessibility Co-Pilot</h1>
              <p className="brand-subtitle">Phase 1 Intelligence • Safety Aware</p>
            </div>
          </div>
          <div className="topbar-actions">
            <div className="live-pill">
              <span className="live-dot" />
              <span>System Live</span>
            </div>
            <button className="icon-button" onClick={() => setDarkMode((prev) => !prev)} type="button">
              <span className="material-icons-outlined">{darkMode ? 'light_mode' : 'dark_mode'}</span>
            </button>
          </div>
        </div>
      </header>

      <main className="content-grid">
        <section className="main-browser">
          <BrowserView currentUrl={getLatestUrl(events)} liveViewUrl={getLiveViewUrl(events)} />
        </section>
        <aside className="side-stack">
          <VoicePanel connected={connected} voiceState={voiceState} onSend={sendTranscript} onInterrupt={sendInterrupt} />
          <RiskBadge riskLevel={riskLevel} connected={connected} />
          <ActivityLog events={events} />
        </aside>
      </main>

      <footer className="footer-bar">
        <div className="footer-inner">
          <div className="footer-group">
            <span className="footer-chip">API: Live</span>
            <span className="footer-chip">Planner: Claude</span>
            <span className="footer-chip">Browser: Browserbase + Stagehand</span>
          </div>
          <div className="footer-group">
            <span>v1.0.0</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
