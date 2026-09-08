// Server-relative time avoids reliance on the workstation's wall clock.
function expireRows(root = document) {
  root.querySelectorAll("[data-announcement-expires]").forEach((row) => {
    const remaining = Date.parse(row.dataset.announcementExpires) - Date.parse(row.dataset.serverNow);
    if (!Number.isFinite(remaining) || remaining <= 0) { row.remove(); return; }
    const start = performance.now();
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
async function refreshBanner() {
  if (!banner || refreshing || document.hidden) return;
  refreshing = true;
  try {
    const response = await fetch(banner.dataset.url, { cache: "no-store", credentials: "same-origin" });
    if (!response.ok || response.redirected) throw new Error("Unavailable");
    banner.innerHTML = await response.text();
    expireRows(banner);
  } catch {
    banner.replaceChildren();
  } finally {
    refreshing = false;
  }
}
if (banner) {
  window.setInterval(refreshBanner, 60000);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) banner.replaceChildren();
    else refreshBanner();
  });
}
