const riskClass = {
  SAFE: 'safe',
  CAUTION: 'caution',
  HIGH_RISK: 'high-risk',
  DANGER: 'danger',
};

export default function RiskBadge({ riskLevel }) {
  return (
    <section className="panel">
      <header>
        <h2>Risk Status</h2>
      </header>
      <div className={`risk-badge ${riskClass[riskLevel] || 'safe'}`}>{riskLevel}</div>
    </section>
  );
}
