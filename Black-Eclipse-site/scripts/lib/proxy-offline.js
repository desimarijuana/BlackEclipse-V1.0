// The front door's "the app is not running" response.
//
// The proxy is the ONLY process that can answer when the Next server is down,
// so it must never hand the browser a bare connection error or a plain-text 502.
// It serves the SAME branded page the service worker caches
// (`src/app/offline/route.ts` → `src/lib/offline/page.ts`), so the two paths are
// visually identical whichever one the browser ends up on.
//
// The page is rendered by the app (with the user's theme) and cached here:
//   * memory — the fast path, refreshed while the app is up,
//   * `.black-eclipse/offline.html` — survives a proxy restart / reboot,
//   * a built-in fallback — used only before the app has ever rendered one.
//
// Everything here is synchronous and dependency-free: it must work on a machine
// where neither the app nor a theme database can be read.

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const CACHE_FILE = path.join(ROOT, ".black-eclipse", "offline.html");
const MAX_BYTES = 512 * 1024;

let cached = null;

/** Navigation detection: only a PAGE gets the offline card; assets get a 503. */
function isNavigation(req) {
  if (!req) return false;
  if (req.method !== "GET" && req.method !== "HEAD") return false;
  const mode = String(req.headers["sec-fetch-mode"] || "").toLowerCase();
  if (mode === "navigate") return true;
  // Browsers label a top-level page load `navigate`, but not every client does
  // (a plain HTTP client, or a fetch that reloads the document). The Accept
  // header decides for those: an asset probe asks for `*/*`, a page asks for
  // HTML.
  const accept = String(req.headers.accept || "").toLowerCase();
  return accept.includes("text/html");
}

function loadCachedPage() {
  if (cached !== null) return cached;
  try {
    const stat = fs.statSync(CACHE_FILE);
    if (stat.size > 0 && stat.size <= MAX_BYTES) cached = fs.readFileSync(CACHE_FILE, "utf8");
    else cached = "";
  } catch {
    cached = "";
  }
  return cached;
}

function saveCachedPage(html) {
  const body = String(html || "");
  // Refuse an obvious error document: caching a 404 page would replace the
  // branded offline card with the app's "not found" screen forever.
  if (!body || body.length > MAX_BYTES || !/offline/i.test(body)) return false;
  cached = body;
  try {
    fs.mkdirSync(path.dirname(CACHE_FILE), { recursive: true });
    fs.writeFileSync(CACHE_FILE, body);
  } catch {
    /* memory copy is still useful */
  }
  return true;
}

// Shipped fallback: the same layout and wording as the real page, in the shipped
// Eclipse palette. Used only if the app has never rendered /offline on this
// install (first launch ever is already down), so it must be tiny and complete.
const FALLBACK_HTML = `<!doctype html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BlackEclipse is offline</title>
<style>
  :root{--bg:#000;--fg:#f4f4f5;--brand:#b4ff42;--on-brand:#0a0a0a;--line:#2a2a2e;
    --card:rgba(18,18,20,.82);
    --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
    --mono:"JetBrains Mono","IBM Plex Mono","SF Mono",Consolas,monospace}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:grid;place-items:center;padding:32px 20px;
    background:var(--bg);color:var(--fg);font:14px/1.55 var(--font);-webkit-font-smoothing:antialiased}
  body::before{content:"";position:fixed;inset:0;pointer-events:none;
    background:radial-gradient(60rem 40rem at 50% 8%,rgba(180,255,66,.10),transparent 62%)}
  main{position:relative;width:min(540px,100%)}
  .card{position:relative;padding:30px;border:1px solid var(--line);border-radius:.9rem;
    background:var(--card);backdrop-filter:blur(18px) saturate(1.35);
    box-shadow:0 24px 70px rgba(0,0,0,.6);overflow:hidden}
  .card::before{content:"";position:absolute;inset:0 0 auto;height:1px;
    background:linear-gradient(90deg,transparent,rgba(180,255,66,.65),transparent)}
  .mark{display:flex;align-items:center;gap:9px;margin-bottom:22px;font-weight:600;letter-spacing:-.01em}
  .glyph{width:22px;height:22px;border-radius:50%;background:var(--brand);
    color:var(--on-brand);font:700 12px/22px var(--font);text-align:center}
  .pill{display:inline-flex;align-items:center;gap:8px;margin-bottom:14px;padding:5px 10px;
    border:1px solid rgba(180,255,66,.22);border-radius:999px;background:rgba(180,255,66,.07);
    font:500 10.5px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase}
  .dot{width:6px;height:6px;border-radius:50%;background:var(--brand)}
  h1{margin:0 0 10px;font-size:26px;line-height:1.2;font-weight:600;letter-spacing:-.02em}
  .lead{margin:0 0 20px;max-width:40ch;font-size:13.5px;line-height:1.65;opacity:.68}
  .steps{margin:0 0 20px;padding:14px 16px;border:1px solid var(--line);border-radius:.7rem;
    background:rgba(255,255,255,.03);font-size:12.5px;line-height:1.6}
  code{display:inline-block;margin:8px 0;padding:6px 10px;border:1px solid var(--line);
    border-radius:.45rem;background:rgba(255,255,255,.05);color:var(--brand);
    font:500 11.5px/1.4 var(--mono)}
  .actions{display:flex;align-items:center;gap:12px}
  button{appearance:none;cursor:pointer;padding:9px 16px;border:1px solid rgba(180,255,66,.5);
    border-radius:.5rem;background:var(--brand);color:var(--on-brand);
    font:600 12.5px/1 var(--font)}
  .host{margin:0;font:10.5px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;opacity:.35}
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<main>
  <section class="card">
    <div class="mark"><span class="glyph">E</span>BlackEclipse</div>
    <div class="pill"><span class="dot"></span><span id="status">Looking for BlackEclipse&hellip;</span></div>
    <h1>BlackEclipse is offline</h1>
    <p class="lead">The app is not running on this computer right now. Nothing is broken &mdash;
      the local server has simply stopped.</p>
    <div class="steps">
      Start it again from the BlackEclipse icon, or run:<br>
      <code>black eclipse</code><br>
      Keep this page open &mdash; it reconnects on its own the moment the app is back.
    </div>
    <div class="actions">
      <button id="retry" type="button">Start BlackEclipse</button>
      <p class="host" id="host"></p>
    </div>
  </section>
</main>
<script>
(function () {
  var host = document.getElementById('host');
  try { host.textContent = location.host; } catch (e) {}
  function probe(url, opts) { return fetch(url, opts || { cache: 'no-store' }); }
  function look() {
    probe('/branding/FAVICON.svg?probe=' + Date.now())
      .then(function (r) { if (r.ok) location.replace('/'); else setTimeout(look, 2000); })
      .catch(function () { setTimeout(look, 2000); });
  }
  document.getElementById('retry').addEventListener('click', function () {
    var status = document.getElementById('status');
    status.textContent = 'Starting BlackEclipse\u2026';
    probe('/__eclipse/start', {
      method: 'POST',
      headers: { 'x-eclipse-control': '1' },
      cache: 'no-store'
    }).catch(function () {}).then(function () { setTimeout(look, 1200); });
  });
  look();
})();
</script>
</body>
</html>`;

/** The page to serve for a navigation while the app is down. */
function offlinePage() {
  return loadCachedPage() || FALLBACK_HTML;
}

module.exports = {
  CACHE_FILE,
  FALLBACK_HTML,
  isNavigation,
  loadCachedPage,
  saveCachedPage,
  offlinePage,
};
