// Server-relative time avoids reliance on the workstation's wall clock.
// Initial rows also spend part of their lifetime in navigation before this runs.
function expireRows(root = document, start = 0) {
  root.querySelectorAll("[data-announcement-expires]").forEach((row) => {
    const remaining = Date.parse(row.dataset.announcementExpires) - Date.parse(row.dataset.serverNow);
    if (!Number.isFinite(remaining) || remaining <= 0) { row.remove(); return; }
    const expire = () => {
      const left = remaining - (performance.now() - start);
      if (left <= 0) row.remove();
      else window.setTimeout(expire, Math.min(left, 2147483647));
    };
    expire();
  });
}
expireRows();
const banner = document.getElementById("staff-announcement-banner");
let refreshing = false;
let generation = 0;
async function refreshBanner() {
  if (!banner || refreshing || document.hidden) return;
  refreshing = true;
  const requestGeneration = ++generation;
  // Charge the full request/body delay conservatively against server lifetime.
  const start = performance.now();
  try {
    const response = await fetch(banner.dataset.url, { cache: "no-store", credentials: "same-origin" });
    if (!response.ok || response.redirected) throw new Error("Unavailable");
    const html = await response.text();
    if (requestGeneration !== generation || document.hidden) return;
    banner.innerHTML = html;
    expireRows(banner, start);
  } catch {
    if (requestGeneration === generation) banner.replaceChildren();
  } finally {
    if (requestGeneration === generation) refreshing = false;
  }
}
if (banner) {
  refreshBanner();
  window.setInterval(refreshBanner, 60000);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      // A pre-hide response must never publish into a resumed session.
      generation += 1;
      refreshing = false;
      banner.replaceChildren();
    }
    else refreshBanner();
  });
}
