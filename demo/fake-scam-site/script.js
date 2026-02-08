function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatSeconds(totalSeconds) {
  const safe = Math.max(0, totalSeconds);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  return `${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}`;
}

function startCountdown() {
  const el = document.getElementById("countdown-value");
  if (!el) return;

  const fromAttr = Number.parseInt(el.dataset.startSeconds || "", 10);
  let remaining = Number.isFinite(fromAttr) ? fromAttr : 0;
  el.textContent = formatSeconds(remaining);

  const timer = window.setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      remaining = 0;
      el.textContent = formatSeconds(remaining);
      window.clearInterval(timer);
      return;
    }
    el.textContent = formatSeconds(remaining);
  }, 1000);
}

startCountdown();
