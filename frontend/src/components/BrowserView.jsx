export default function BrowserView({ currentUrl, liveViewUrl }) {
  return (
    <section className="panel browser-shell">
      <div className="browser-header">
        <div className="browser-dots">
          <span />
          <span />
          <span />
        </div>
        <div className="browser-address">
          <span className="material-icons-outlined">lock</span>
          <span className="truncate">{currentUrl || 'about:blank'}</span>
          <span className="material-icons-outlined">refresh</span>
        </div>
      </div>
      <div className="browser-frame">
        {liveViewUrl ? (
          <iframe
            src={liveViewUrl}
            title="Browserbase Live View"
            className="live-view-frame"
            allow="clipboard-read; clipboard-write"
          />
        ) : (
          <div className="browser-placeholder">
            <div className="placeholder-icon">
              <span className="material-icons-outlined">language</span>
            </div>
            <h3>Browserbase Live View</h3>
            <p>
              Initializing secure browser session. Current URL:
              {' '}
              <code>{currentUrl || 'about:blank'}</code>
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
