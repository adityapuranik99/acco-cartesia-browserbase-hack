export default function ActivityLog({ events }) {
  const recent = events.slice(-18).reverse();

  return (
    <section className="panel activity-panel">
      <header className="card-title-row">
        <h2 className="card-title">
          <span className="material-icons-outlined">history</span>
          Activity Log
        </h2>
      </header>
      <ul className="log-list">
        {recent.map((event, index) => (
          <li key={`${event.type}-${index}`}>
            <span className="timeline-dot" />
            <div>
              <strong>{event.type}</strong>
              <span>{event.text || event.url || event.risk_level || ''}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
