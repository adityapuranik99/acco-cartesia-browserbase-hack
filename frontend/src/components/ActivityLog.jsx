export default function ActivityLog({ events }) {
  const recent = events.slice(-18).reverse();
  const formatEventText = (event) => {
    if (event.type === 'voice_state') {
      return event.text || event.voice_state || '';
    }
    return event.text || event.url || event.risk_level || '';
  };

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
              <strong>{event.type === 'voice_state' ? `voice_state:${event.voice_state || ''}` : event.type}</strong>
              <span>{formatEventText(event)}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
