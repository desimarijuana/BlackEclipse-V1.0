// Desktop-launch progress page.
//
// The desktop launcher runs with a HIDDEN console, so before this page existed a
// double-click showed NOTHING until the app was fully up. A cold production
// build takes minutes, a proxy that fails to bind never finishes, and a crashed
// server exits silently — in all three cases the icon looked "stuck" with no
// window, no error and no way to tell what happened.
//
// This is a tiny loopback-only HTTP server the launcher opens IMMEDIATELY. It
// shows the real phase (building / starting / waiting for the proxy), the last
// server output line, and an honest error panel with the log path if boot
// fails. When the app is ready the page redirects itself to the real URL.
//
// The page renders with the USER'S APP-WIDE THEME (JDDS `SystemConfig` →
// `eclipse_theme`, read by ./app-theme.js): their brand color, scheme (dark or
// light), font stacks, radius, glass settings, background treatment and logo.
// The shipped wordmark/favicon are served from `public/branding`; a custom
// uploaded logo/favicon (or a file under public/) replaces them.
//
// Design: zero dependencies, no build step, no external assets (a local page
// must paint instantly on a machine that is busy compiling). The page polls
// `/status`; the launcher pushes state through `update()` / `ready()` / `fail()`.

const http = require("http");
const fs = require("fs");
const path = require("path");
const { sanitizeTheme, imageBytes, DEFAULT_THEME } = require("./app-theme");

const ROOT = path.join(__dirname, "..", "..");
const DEFAULT_LOGO = path.join(ROOT, "public", "branding", "LOGO-WORDMARK.svg");
const DEFAULT_MARK = path.join(ROOT, "public", "branding", "FAVICON.svg");

// The page is a constant string: the only values interpolated into it come from
// a sanitized theme (hex colors, clamped numbers, stripped font stacks), never
// from request data. All dynamic text arrives through `/status` as JSON and is
// written with textContent.
const PAGE = `<!doctype html>
<html lang="en" class="__SCHEME_CLASS__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Starting __APP_NAME__</title>
<link rel="icon" href="/favicon">
<!--APP_THEME-->
<style>
  /* Structure comes from the app's frosted-glass system. Every brand value is a
   * CSS variable supplied by the injected app-theme block above, so this page
   * follows Settings › Customization without duplicating the palette here. */
  * { box-sizing: border-box; }
  html, body { min-height: 100%; }
  body {
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 32px;
    background: var(--bg);
    color: var(--fg);
    font: 14px/1.55 var(--font-sans);
    -webkit-font-smoothing: antialiased;
  }
  /* The page treatment follows the theme: grid shows only for the "grid"
   * background, gradient adds a second wash, solid stays flat. The brand glow
   * is on unless the theme turns "glow" off. */
  body::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background-image:
      linear-gradient(rgb(var(--brand-rgb) / var(--grid-alpha)) 1px, transparent 1px),
      linear-gradient(90deg, rgb(var(--brand-rgb) / var(--grid-alpha)) 1px, transparent 1px);
    background-size: 44px 44px;
    mask-image: radial-gradient(closest-side at 50% 42%, #000 25%, transparent 100%);
    -webkit-mask-image: radial-gradient(closest-side at 50% 42%, #000 25%, transparent 100%);
  }
  body::after {
    content: "";
    position: fixed;
    inset: -25%;
    pointer-events: none;
    background: var(--wash),
      radial-gradient(closest-side at 50% 34%, rgb(var(--brand-rgb) / var(--glow-alpha)), transparent 72%);
  }
  main { position: relative; width: min(580px, 100%); }
  /* .glass-card from globals.css, with the user's tint/blur/opacity/radius. */
  .card {
    position: relative;
    padding: 22px 24px 18px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--card-bg);
    backdrop-filter: var(--card-blur);
    box-shadow: var(--card-shadow);
    overflow: hidden;
  }
  .card::before {
    content: "";
    position: absolute;
    inset: 0 0 auto;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgb(var(--brand-rgb) / 0.6), transparent);
    opacity: 0.8;
  }
  header { display: flex; align-items: center; min-height: 23px; }
  .logo { display: block; height: var(--logo-height); width: auto; }
  /* The shipped wordmark is white; on a light theme it must invert. A custom
   * uploaded logo keeps its own colors. */
  html:not(.dark) .logo-shipped { filter: invert(1); }
  .logo-fallback {
    display: none;
    color: var(--fg);
    font: 600 13px/1 var(--font-sans);
    letter-spacing: 0.2em;
    text-transform: uppercase;
  }

  h1 {
    margin: 20px 0 4px;
    color: var(--fg);
    font-family: var(--font-heading);
    font-size: 20px;
    line-height: 1.3;
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .phase { color: rgb(var(--text-rgb) / 0.66); font-size: 13.5px; min-height: 42px; }

  .bar {
    position: relative;
    height: 3px;
    margin: 16px 0 9px;
    border-radius: 999px;
    background: rgb(var(--text-rgb) / 0.08);
    overflow: hidden;
  }
  .bar i {
    position: absolute;
    inset: 0;
    width: 34%;
    border-radius: 999px;
    background: linear-gradient(90deg, transparent, var(--brand), var(--brand-accent), transparent);
    animation: slide 1.45s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }
  .bar.done i { width: 100%; animation: none; background: linear-gradient(90deg, var(--brand), var(--brand-accent)); }
  .bar.err i { width: 100%; animation: none; background: var(--danger); }
  @keyframes slide { from { transform: translateX(-110%); } to { transform: translateX(320%); } }

  .meta {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    font: 10.5px/1.4 var(--font-mono);
    letter-spacing: 0.08em;
    color: rgb(var(--text-rgb) / 0.40);
    text-transform: uppercase;
  }
  .hint {
    margin: 14px 0 0;
    font-size: 12.5px;
    line-height: 1.6;
    color: rgb(var(--text-rgb) / 0.55);
    min-height: 36px;
  }

  .error {
    display: none;
    margin-top: 16px;
    padding: 12px 14px;
    border: 1px solid var(--danger-border);
    border-radius: 10px;
    background: var(--danger-surface);
  }
  .error.show { display: block; }
  .error h2 { margin: 0 0 4px; font-size: 13px; font-weight: 600; color: var(--danger); }
  .error p { margin: 0; font-size: 12.5px; color: rgb(var(--text-rgb) / 0.72); }
  a.btn {
    display: inline-block;
    margin-top: 10px;
    padding: 7px 13px;
    border-radius: calc(var(--radius) * 0.7);
    background: var(--brand);
    color: var(--on-brand);
    font: 600 12px/1 var(--font-sans);
    text-decoration: none;
  }

  details { margin-top: 16px; border-top: 1px solid rgb(var(--text-rgb) / 0.10); padding-top: 11px; }
  summary {
    cursor: pointer;
    user-select: none;
    font: 500 10px/1 var(--font-mono);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: rgb(var(--text-rgb) / 0.40);
  }
  .tail {
    margin: 10px 0 0;
    padding: 10px 12px;
    max-height: 170px;
    overflow: auto;
    border: 1px solid rgb(var(--text-rgb) / 0.08);
    border-radius: calc(var(--radius) * 0.7);
    background: rgb(var(--text-rgb) / 0.04);
    color: rgb(var(--text-rgb) / 0.72);
    font: 11px/1.55 var(--font-mono);
    white-space: pre-wrap;
    word-break: break-word;
  }
  .paths {
    margin-top: 8px;
    color: rgb(var(--text-rgb) / 0.34);
    font: 10.5px/1.6 var(--font-mono);
    word-break: break-all;
  }
  footer {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-top: 16px;
    padding-top: 11px;
    border-top: 1px solid rgb(var(--text-rgb) / 0.07);
    color: rgb(var(--text-rgb) / 0.30);
    font: 10px/1.4 var(--font-mono);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
</style>
</head>
<body>
<main>
  <div class="card">
    <header>
      <img class="logo __LOGO_CLASS__" id="logo" src="/logo" alt="__APP_NAME__" onerror="this.style.display='none';document.getElementById('logoFallback').style.display='block'">
      <span class="logo-fallback" id="logoFallback">__APP_NAME__</span>
    </header>
    <h1 id="title">Starting __APP_NAME__</h1>
    <p class="phase" id="phase">Preparing the launcher…</p>
    <div class="bar" id="bar"><i></i></div>
    <div class="meta"><span id="elapsed">0:00</span><span id="detail"></span></div>
    <p class="hint" id="hint"></p>
    <div class="error" id="error">
      <h2>The app did not start</h2>
      <p id="errorMsg"></p>
      <a class="btn" id="retry" href="" style="display:none">Open __APP_NAME__</a>
    </div>
    <details>
      <summary>Details and logs</summary>
      <pre class="tail" id="tail">(no output yet)</pre>
      <div class="paths" id="paths"></div>
    </details>
    <footer>
      <span>Local launch · 127.0.0.1</span>
      <span>Production</span>
    </footer>
  </div>
</main>
<script>
(function () {
  var started = Date.now();
  var $ = function (id) { return document.getElementById(id); };
  var finished = false;

  setInterval(function () {
    var s = Math.floor((Date.now() - started) / 1000);
    $('elapsed').textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }, 250);

  function stop(phase, title, barClass) {
    $('phase').textContent = phase;
    $('bar').className = 'bar ' + barClass;
    if (title) $('title').textContent = title;
  }

  async function tick() {
    var st = null;
    try {
      var res = await fetch('/status', { cache: 'no-store' });
      st = await res.json();
    } catch (e) {
      setTimeout(tick, 900);
      return;
    }
    if (!st) { setTimeout(tick, 900); return; }

    $('paths').textContent = 'launcher: ' + (st.logPath || '') + '\\nserver:   ' + (st.serverLogPath || '');
    $('tail').textContent = st.tail || '(no output yet)';

    if (st.ready && st.url) {
      stop('Ready — opening the app…', null, 'done');
      $('detail').textContent = 'ready';
      $('hint').textContent = '';
      if (!finished) {
        finished = true;
        setTimeout(function () { window.location.replace(st.url); }, 220);
        setTimeout(function () {
          stop('Ready.', null, 'done');
          $('hint').textContent = 'If nothing opened, use the button below.';
          $('error').classList.add('show');
          $('errorMsg').textContent = 'The app answered but this page was not redirected.';
          $('retry').style.display = 'inline-block';
          $('retry').href = st.url;
        }, 4000);
      }
      return;
    }

    if (st.error) {
      stop('Stopped.', null, 'err');
      $('detail').textContent = 'failed';
      $('hint').textContent = 'Close this tab and double-click the icon to try again.';
      $('error').classList.add('show');
      $('errorMsg').textContent = st.error.message || 'Unknown error.';
      $('retry').style.display = 'none';
      return;
    }

    $('phase').textContent = st.detail || 'Starting…';
    $('detail').textContent = st.phase || '';
    $('hint').textContent = st.hint || '';
    setTimeout(tick, 450);
  }

  window.addEventListener('pagehide', function () {
    try { navigator.sendBeacon && navigator.sendBeacon('/closed'); } catch (e) {}
  });

  tick();
})();
</script>
</body>
</html>`;

const PHASE_COPY = {
  preparing: {
    hint: "Checking the build and the environment.",
  },
  building: {
    hint: "The first launch (or a launch after a source change) compiles the production bundle. This happens once — later launches start in about two seconds. You can leave this tab open.",
  },
  starting: {
    hint: "The server is booting. This usually takes a couple of seconds.",
  },
  proxy: {
    hint: "The app is running; waiting for the local hostname proxy (https://blackeclipse) to answer.",
  },
  ready: { hint: "" },
  error: { hint: "" },
};

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Relative luminance, used to pick readable text on the brand button.
function luminance(hex) {
  const v = String(hex || "#000000").replace("#", "");
  const full = v.length === 3 ? v.split("").map((c) => c + c).join("") : v;
  const n = parseInt(full, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const lin = (c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** CSS for the user's saved theme. Values are already sanitized by app-theme. */
function themeCss(t) {
  const dark = t.scheme === "dark";
  const blur = t.glass.enabled ? `blur(${t.glass.blur}px) saturate(1.35)` : "none";
  const cardBg = t.glass.enabled
    ? `rgb(${t.surfaceRgb} / ${t.glass.opacity})`
    : `rgb(${t.surfaceRgb} / 0.96)`;
  const shadowAlpha = dark
    ? { none: 0, soft: 0.3, medium: 0.42, dramatic: 0.55 }[t.shadow]
    : { none: 0, soft: 0.08, medium: 0.12, dramatic: 0.18 }[t.shadow];
  const highlight = dark ? 0.06 : 0.55;
  const cardShadow =
    shadowAlpha === 0
      ? "none"
      : `0 12px 40px rgba(0,0,0,${shadowAlpha}), inset 0 1px 0 rgba(255,255,255,${highlight})`;
  const glowAlpha = !t.glow ? 0 : dark ? 0.11 : 0.07;
  const gridAlpha = t.background === "grid" ? (dark ? 0.05 : 0.045) : 0;
  const wash =
    t.background === "gradient"
      ? `radial-gradient(closest-side at 28% 18%, rgb(${t.primaryRgb} / ${dark ? 0.12 : 0.08}), transparent 70%), radial-gradient(closest-side at 76% 82%, rgb(${t.accentRgb} / ${dark ? 0.1 : 0.07}), transparent 70%)`
      : "none";
  const danger = dark ? "#ff5c5c" : "#c81e1e";
  const dangerSurface = dark ? "rgba(255, 92, 92, 0.07)" : "rgba(200, 30, 30, 0.06)";
  const dangerBorder = dark ? "rgba(255, 92, 92, 0.3)" : "rgba(200, 30, 30, 0.25)";
  const onBrand = luminance(t.colors.primary) > 0.45 ? "#0a0a0a" : "#ffffff";

  return `<style id="app-theme">
  :root {
    --bg: ${t.colors.background};
    --fg: ${t.colors.text};
    --text-rgb: ${t.textRgb};
    --brand: ${t.colors.primary};
    --brand-rgb: ${t.primaryRgb};
    --brand-accent: ${t.colors.accent};
    --accent-rgb: ${t.accentRgb};
    --border: ${t.colors.border};
    --card-bg: ${cardBg};
    --card-blur: ${blur};
    --card-shadow: ${cardShadow};
    --radius: ${t.radius}rem;
    --logo-height: ${(23 * t.logoScale).toFixed(1)}px;
    --font-sans: ${t.fontUi};
    --font-heading: ${t.fontUi};
    --font-mono: ${t.fontMono};
    --glow-alpha: ${glowAlpha};
    --grid-alpha: ${gridAlpha};
    --wash: ${wash};
    --on-brand: ${onBrand};
    --danger: ${danger};
    --danger-surface: ${dangerSurface};
    --danger-border: ${dangerBorder};
  }
</style>`;
}

function renderPage(theme) {
  const logoClass = theme.logoUrl ? "logo-custom" : "logo-shipped";
  return PAGE
    .replace("__SCHEME_CLASS__", theme.scheme === "light" ? "" : "dark")
    .replace("<!--APP_THEME-->", themeCss(theme))
    .replace("__LOGO_CLASS__", logoClass)
    .replace(/__APP_NAME__/g, escapeHtml(theme.appName));
}

function probe(url, timeoutMs) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (c) => {
        body += c;
        if (body.length > 64 * 1024) res.destroy();
      });
      res.on("end", () => resolve({ status: res.statusCode, body }));
      res.on("error", () => resolve(null));
    });
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
    req.on("error", () => resolve(null));
  });
}

function sendFile(res, file) {
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404, { "cache-control": "no-store" }).end();
      return;
    }
    res.writeHead(200, {
      "content-type": "image/svg+xml; charset=utf-8",
      "cache-control": "no-cache",
    });
    res.end(data);
  });
}

// The user's uploaded logo wins; otherwise the shipped wordmark/favicon.
function sendImage(res, ref, fallbackFile) {
  const custom = imageBytes(ref);
  if (!custom) {
    sendFile(res, fallbackFile);
    return;
  }
  res.writeHead(200, { "content-type": custom.contentType, "cache-control": "no-cache" });
  res.end(custom.data);
}

/**
 * Start the loopback progress page.
 *
 * @param {object} options
 * @param {number} options.port      preferred port
 * @param {number} [options.tries]   how many consecutive ports to try
 * @param {string} options.url       where to send the browser when ready
 * @param {string} options.logPath   launcher log (shown in the UI)
 * @param {string} options.serverLogPath  server log (shown in the UI)
 * @param {object} [options.theme]   sanitized theme from ./app-theme
 * @param {() => void} [options.onClosed] called when the tab is closed
 */
async function createSplash(options) {
  const {
    url,
    logPath = "",
    serverLogPath = "",
    tries = 8,
    theme,
    onClosed,
  } = options || {};
  const preferred = Number(options && options.port) || 0;
  const activeTheme = theme && theme.colors ? theme : sanitizeTheme(DEFAULT_THEME);
  const page = renderPage(activeTheme);

  const state = {
    phase: "preparing",
    detail: "Preparing the launcher…",
    hint: PHASE_COPY.preparing.hint,
    ready: false,
    error: null,
    url: url || "",
    tail: "",
    pid: process.pid,
    startedAt: Date.now(),
    logPath,
    serverLogPath,
    theme: {
      scheme: activeTheme.scheme,
      primary: activeTheme.colors.primary,
      source: activeTheme.source || "db",
    },
  };

  let closed = false;
  const server = http.createServer((req, res) => {
    const route = (req.url || "/").split("?")[0];
    if (route === "/status") {
      res.writeHead(200, {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
      });
      res.end(JSON.stringify({ ...state, elapsedMs: Date.now() - state.startedAt }));
      return;
    }
    if (route === "/logo") {
      sendImage(res, activeTheme.logoUrl, DEFAULT_LOGO);
      return;
    }
    if (route === "/favicon") {
      sendImage(res, activeTheme.faviconUrl, DEFAULT_MARK);
      return;
    }
    if (route === "/closed" && req.method === "POST") {
      closed = true;
      res.writeHead(204).end();
      try {
        onClosed && onClosed();
      } catch {
        /* best effort */
      }
      return;
    }
    if (route === "/" || route === "/index.html") {
      res.writeHead(200, {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
      });
      res.end(page);
      return;
    }
    res.writeHead(404).end();
  });

  const port = await new Promise((resolve) => {
    let attempt = 0;
    const tryListen = (candidate) => {
      const onError = (err) => {
        server.removeListener("error", onError);
        attempt += 1;
        if (err && err.code === "EADDRINUSE" && attempt < tries) {
          tryListen(candidate + 1);
          return;
        }
        resolve(0);
      };
      server.once("error", onError);
      server.listen(candidate, "127.0.0.1", () => {
        server.removeListener("error", onError);
        resolve(candidate);
      });
    };
    tryListen(preferred);
  });

  if (!port) return null;
  // A late socket error on the progress page must never take the launcher down.
  server.on("error", () => {});
  // Never keep the process alive by itself: the launcher owns the lifecycle.
  try {
    server.unref();
  } catch {
    /* older Node */
  }

  return {
    port,
    url: `http://127.0.0.1:${port}/`,
    state,
    theme: activeTheme,
    update(patch) {
      if (closed) return;
      if (patch.phase && patch.phase !== state.phase) {
        state.phase = patch.phase;
        state.hint = (PHASE_COPY[patch.phase] || PHASE_COPY.preparing).hint;
      }
      if (typeof patch.detail === "string") state.detail = patch.detail;
      if (typeof patch.tail === "string") state.tail = patch.tail;
      if (typeof patch.hint === "string") state.hint = patch.hint;
      if (typeof patch.url === "string") state.url = patch.url;
    },
    ready(finalUrl) {
      if (finalUrl) state.url = finalUrl;
      state.phase = "ready";
      state.hint = "";
      state.detail = "Opening the app…";
      state.ready = true;
    },
    fail(message, detail) {
      state.phase = "error";
      state.hint = "";
      state.detail = "Stopped.";
      state.ready = false;
      state.error = { message: message || "Unknown error.", at: Date.now() };
      if (detail) state.tail = detail;
    },
    close() {
      closed = true;
      try {
        server.close();
      } catch {
        /* already closed */
      }
    },
    get closed() {
      return closed;
    },
  };
}

/**
 * Discover a splash page that belongs to a launcher that is STILL ALIVE.
 * A second double-click uses this to attach to the first launcher's progress
 * page instead of starting a competing boot.
 */
async function findSplash({ port, tries = 8, pidAlive } = {}) {
  const base = Number(port) || 3197;
  const probes = [];
  for (let i = 0; i < tries; i += 1) {
    const candidate = base + i;
    probes.push(
      probe(`http://127.0.0.1:${candidate}/status`, 350).then((res) => {
        if (!res || res.status !== 200) return null;
        let parsed;
        try {
          parsed = JSON.parse(res.body);
        } catch {
          return null;
        }
        if (!parsed || typeof parsed.pid !== "number") return null;
        if (typeof pidAlive === "function" && !pidAlive(parsed.pid)) return null;
        return { port: candidate, url: `http://127.0.0.1:${candidate}/`, state: parsed };
      })
    );
  }
  const found = await Promise.all(probes);
  return found.find(Boolean) || null;
}

module.exports = { createSplash, findSplash, renderPage, themeCss, PAGE };
