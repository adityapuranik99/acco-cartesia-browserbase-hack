export default function BrowserView({ currentUrl, liveViewUrl }) {
  return (
    <section className="panel browser-panel">
      <header>
        <h2>Browser View</h2>
        <p className="muted">Browserbase Live View</p>
      </header>
      <div className="browser-frame">
        {liveViewUrl ? (
          <iframe
            src={liveViewUrl}
            title="Browserbase Live View"
            className="live-view-frame"
            allow="clipboard-read; clipboard-write"
          />
        ) : (
          <>
            <p>Live view not ready yet. Current URL:</p>
            <code>{currentUrl || 'about:blank'}</code>
          </>
        )}
      </div>
    </section>
  );
}
