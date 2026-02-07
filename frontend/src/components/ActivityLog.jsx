export default function ActivityLog({ events }) {
  const recent = events.slice(-12).reverse();

  return (
    <section className="panel">
      <header>
        <h2>Activity Log</h2>
      </header>
      <ul className="log-list">
        {recent.map((event, index) => (
          <li key={`${event.type}-${index}`}>
            <strong>{event.type}</strong>
            <span>{event.text || event.url || event.risk_level || ''}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
