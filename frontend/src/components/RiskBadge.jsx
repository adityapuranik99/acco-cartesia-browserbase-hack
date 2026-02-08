const riskClass = {
  SAFE: 'safe',
  CAUTION: 'caution',
  HIGH_RISK: 'high-risk',
  DANGER: 'danger',
};

export default function RiskBadge({ riskLevel, connected }) {
  return (
    <section className="panel system-panel">
      <header className="card-title-row">
        <h2 className="card-title">
          <span className="material-icons-outlined">analytics</span>
          System Status
        </h2>
      </header>
      <div className="status-grid">
        <div className="status-item">
          <div className="status-label">
            <span className="material-icons-outlined">cable</span>
            <span>WebSocket</span>
          </div>
          <span className={`status-pill ${connected ? 'online' : 'offline'}`}>
            {connected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>
        <div className="status-item">
          <div className="status-label">
            <span className="material-icons-outlined">shield</span>
            <span>Risk Status</span>
          </div>
          <span className={`risk-badge ${riskClass[riskLevel] || 'safe'}`}>{riskLevel}</span>
        </div>
      </div>
    </section>
  );
}
