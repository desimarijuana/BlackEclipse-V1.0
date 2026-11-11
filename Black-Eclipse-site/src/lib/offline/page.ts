// ── Offline "app is not running" page ────────────────────────────────────────
//
// When the local server has stopped (the desktop launcher killed it, `black
// stop`, a crash), the origin refuses the connection and the BROWSER paints its
// own error page. That page is not ours: it has the browser's chrome, the
// browser's wording and none of the app's identity — so a stopped Eclipse looked
// like a broken website instead of a product that is simply asleep.
//
// `public/sw.js` caches THIS document. On a failed navigation it answers with
// the cached copy, so the user sees an Eclipse-branded page that says what
// happened and reconnects itself the moment the app is back.
//
// The document is deliberately self-contained: no font/script/image requests, so
// it renders instantly on a machine where nothing is listening. The logo is
// inlined SVG and every brand value comes from the user's saved theme
// (`themeCssVars`), the same tokens the app and the desktop boot card use.

import {
  DEFAULT_ECLIPSE_THEME,
  normalizeTheme,
  themeCssVars,
  type EclipseTheme,
} from "@/lib/theme/tokens";

export interface OfflinePageInput {
  theme?: EclipseTheme | null;
  /** Trusted inline SVG for the shipped wordmark (`public/branding`). */
  wordmark?: string;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * A theme value is interpolated into a `<style>` block. The theme is local and
 * already sanitized, but strip the characters that could close a declaration, a
 * rule or the stylesheet anyway — no legitimate token needs them (font stacks,
 * colors, gradients, lengths).
 */
function cssValue(value: string): string {
  return value.replace(/[<>{};:\\]/g, "").trim();
}

/** Only a data URL can render with no network; anything else falls back to the wordmark. */
function inlineLogo(theme: EclipseTheme): string | null {
  const url = theme.logoUrl;
  if (typeof url === "string" && /^data:image\/[a-z+]+;base64,/i.test(url)) {
    return `<img class="logo-img" src="${escapeHtml(url)}" alt="${escapeHtml(theme.appName)}" />`;
  }
  return null;
}

function logoMarkup(theme: EclipseTheme, wordmark: string): string {
  const custom = inlineLogo(theme);
  if (custom) return custom;
  if (wordmark.trim()) {
    // The shipped wordmark is white; a light theme inverts it (same rule the
    // desktop boot card uses).
    return `<span class="logo-shape">${wordmark}</span>`;
  }
  const monogram = (theme.logoText || theme.appName.charAt(0) || "E").slice(0, 2).toUpperCase();
  return `<span class="logo-mono">${escapeHtml(monogram)}</span>`;
}

export function renderOfflinePage(input: OfflinePageInput = {}): string {
  const theme = normalizeTheme(input.theme ?? DEFAULT_ECLIPSE_THEME);
  const name = theme.appName || DEFAULT_ECLIPSE_THEME.appName;
  const safeName = escapeHtml(name);
  const wordmark = input.wordmark ?? "";
  const dark = theme.scheme === "dark";

  const vars = themeCssVars(theme);
  const cssDeclarations = Object.entries(vars)
    .map(([key, value]) => `    ${key}: ${cssValue(String(value))};`)
    .join("\n");

  return `<!doctype html>
<html lang="en" class="${dark ? "dark" : "light"}${theme.animations === false ? " motion-off" : ""}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>${safeName} is offline</title>
<link rel="icon" href="/branding/FAVICON.svg">
<style>
  :root {
${cssDeclarations}
  }
  /* The card tint: dark themes use the user's glass tint, light themes the
   * light-safe tint. Mirrors the app's own .glass-card recipe. */
  html.dark { --card-tint: var(--glass-tint); }
  html.light { --card-tint: var(--glass-tint-light); }

  * { box-sizing: border-box; }
  html, body { min-height: 100%; }
  body {
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 32px 20px;
    background-color: var(--background);
    background-image: var(--page-bg-image);
    background-size: var(--page-bg-size);
    color: var(--foreground);
    font: 14px/1.55 var(--font-sans);
    -webkit-font-smoothing: antialiased;
  }
  /* Calm brand glow, same one the app leans on. */
  body::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background: radial-gradient(60rem 40rem at 50% 8%, rgb(var(--brand-rgb) / 0.10), transparent 62%);
  }
  main { position: relative; width: min(540px, 100%); }

  .card {
    position: relative;
    padding: 30px 30px 24px;
    border: 1px solid var(--border);
    border-radius: calc(var(--radius) * 1.5);
    background: rgb(var(--card-tint) / var(--glass-opacity));
    backdrop-filter: blur(var(--glass-blur)) saturate(1.35);
    -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(1.35);
    box-shadow: var(--glass-shadow);
    overflow: hidden;
  }
  .card::before {
    content: "";
    position: absolute;
    inset: 0 0 auto;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgb(var(--brand-rgb) / 0.65), transparent);
  }

  .logo { display: flex; align-items: center; min-height: 26px; margin-bottom: 22px; }
  .logo-shape { display: block; }
  .logo-shape svg { display: block; width: calc(112px * var(--logo-scale)); height: auto; }
  html.light .logo-shape svg { filter: invert(1); }
  .logo-img { display: block; height: calc(26px * var(--logo-scale)); width: auto; }
  .logo-mono {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: calc(var(--radius) * 1.2);
    background: var(--brand);
    color: var(--primary-foreground);
    font: 700 16px/1 var(--font-heading);
    letter-spacing: 0.04em;
  }

  /* Status pill: the one live element. It states what the page is doing. */
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
    padding: 5px 10px 5px 9px;
    border: 1px solid rgb(var(--brand-rgb) / 0.22);
    border-radius: 999px;
    background: rgb(var(--brand-rgb) / 0.07);
    color: var(--foreground);
    font: 500 10.5px/1 var(--font-mono);
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--brand);
    box-shadow: 0 0 0 0 rgb(var(--brand-rgb) / 0.5);
    animation: breathe 2.4s ease-in-out infinite;
  }
  .pill.ok { border-color: rgb(var(--brand-rgb) / 0.45); }
  .pill.ok .dot { animation: none; }
  @keyframes breathe {
    0%, 100% { opacity: 0.55; box-shadow: 0 0 0 0 rgb(var(--brand-rgb) / 0.35); }
    50% { opacity: 1; box-shadow: 0 0 0 4px rgb(var(--brand-rgb) / 0); }
  }

  h1 {
    margin: 0 0 10px;
    font-family: var(--font-heading);
    font-size: 26px;
    line-height: 1.2;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .lead {
    margin: 0 0 20px;
    max-width: 40ch;
    font-size: 13.5px;
    line-height: 1.65;
    opacity: 0.68;
  }

  .steps {
    margin: 0 0 20px;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: calc(var(--radius) * 1.1);
    background: rgb(var(--card-tint) / 0.55);
  }
  .steps p { margin: 0; font-size: 12.5px; line-height: 1.6; opacity: 0.72; }
  .steps p + code { display: block; margin: 8px 0; }
  .steps code {
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: calc(var(--radius) * 0.7);
    background: rgb(var(--foreground) / 0.05);
    color: var(--brand);
    font: 500 11.5px/1.4 var(--font-mono);
    word-break: break-all;
  }
  .steps p:last-child { margin-top: 10px; opacity: 0.55; }

  .actions { display: flex; align-items: center; gap: 12px; }
  button {
    appearance: none;
    cursor: pointer;
    padding: 9px 16px;
    border: 1px solid rgb(var(--brand-rgb) / 0.5);
    border-radius: calc(var(--radius) * 0.75);
    background: var(--brand);
    color: var(--primary-foreground);
    font: 600 12.5px/1 var(--font-sans);
    transition: filter 160ms ease, transform 160ms ease;
  }
  button:hover { filter: brightness(1.07); }
  button:active { transform: translateY(1px); }
  button:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
  .host {
    margin: 0;
    color: var(--foreground);
    font: 10.5px/1.4 var(--font-mono);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    opacity: 0.35;
  }

  footer {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    margin-top: 14px;
    padding: 0 4px;
    color: var(--foreground);
    font: 10px/1.4 var(--font-mono);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    opacity: 0.3;
  }

  .card { animation: rise 380ms cubic-bezier(0.22, 0.7, 0.24, 1) both; }
  @keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
  .motion-off .card, .motion-off .dot { animation: none; }
  @media (prefers-reduced-motion: reduce) {
    .card, .dot { animation: none; }
    button { transition: none; }
  }
</style>
</head>
<body data-app="${safeName}">
<main>
  <section class="card">
    <div class="logo">${logoMarkup(theme, wordmark)}</div>
    <div class="pill" id="pill"><span class="dot"></span><span id="status">Looking for ${safeName}&hellip;</span></div>
    <h1>${safeName} is offline</h1>
    <p class="lead">
      The app is not running on this computer right now. Nothing is broken &mdash;
      the local server has simply stopped.
    </p>
    <div class="steps">
      <p>Start it again from the ${safeName} icon, or press the button below.</p>
      <code>black eclipse</code>
      <p>Keep this page open &mdash; it reconnects on its own the moment the app is back.</p>
    </div>
    <div class="actions">
      <button id="retry" type="button">Start ${safeName}</button>
      <p class="host" id="host"></p>
    </div>
  </section>
  <footer><span>Local app &middot; 127.0.0.1</span><span id="foot"></span></footer>
</main>
<noscript>
  <p style="text-align:center;opacity:.6;font-size:12px">
    Reopen this page after starting ${safeName}.
  </p>
</noscript>
<script>
(function () {
  var name = document.body.getAttribute('data-app') || 'the app';
  var statusEl = document.getElementById('status');
  var pill = document.getElementById('pill');
  var hostEl = document.getElementById('host');
  var footEl = document.getElementById('foot');
  var done = false;
  var tries = 0;
  var timer = null;

  try {
    if (hostEl) hostEl.textContent = location.host;
    if (footEl) footEl.textContent = location.protocol === 'https:' ? 'Secure' : 'Local';
  } catch (e) {}

  function setStatus(text, ok) {
    if (statusEl) statusEl.textContent = text;
    if (pill) pill.className = ok ? 'pill ok' : 'pill';
  }

  // Probe a static asset, not the page: it is served without auth, without a
  // DB read and without running the app's middleware, so a 200 here means the
  // server is genuinely back. The front door answers a stopped app with the
  // branded page for NAVIGATIONS only; everything else gets a 503, so this probe
  // can never mistake "the door is up" for "the app is up".
  function check() {
    if (done) return;
    if (timer) { clearTimeout(timer); timer = null; }
    fetch('/branding/FAVICON.svg?probe=' + Date.now(), { cache: 'no-store' })
      .then(function (res) {
        if (!res || !res.ok) throw new Error('not ready');
        done = true;
        setStatus('Reconnected \u2014 opening ' + name + '\u2026', true);
        setTimeout(function () { location.replace('/'); }, 320);
      })
      .catch(function () {
        tries += 1;
        if (tries >= 3) setStatus('Still waiting \u2014 press Start ' + name + ' or open its icon', false);
        timer = setTimeout(check, 2000);
      });
  }

  // The front door can boot the app on this click (POST /__eclipse/start),
  // so a stopped server is one button away instead of a trip to the desktop.
  function start() {
    done = false;
    tries = 0;
    setStatus('Starting ' + name + '\u2026', false);
    fetch('/__eclipse/start', {
      method: 'POST',
      headers: { 'x-eclipse-control': '1' },
      cache: 'no-store',
    })
      .then(function (res) {
        setStatus(
          res && (res.status === 202 || res.ok)
            ? 'Starting ' + name + ' \u2014 this can take a moment\u2026'
            : 'Waiting for ' + name + ' \u2014 start it from its icon',
          false
        );
      })
      .catch(function () {
        setStatus('Waiting for ' + name + ' \u2014 start it from its icon', false);
      })
      .then(function () { timer = setTimeout(check, 1200); });
  }

  var retry = document.getElementById('retry');
  if (retry) retry.addEventListener('click', start);
  window.addEventListener('online', check);
  window.addEventListener('focus', check);
  check();
})();
</script>
</body>
</html>`;
}
