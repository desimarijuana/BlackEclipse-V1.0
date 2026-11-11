#!/usr/bin/env node
// Local hostname front door — `npm run proxy`.
//
// BlackEclipse normally runs on http://localhost:3000. This is a tiny,
// ZERO-DEPENDENCY reverse proxy (Node's built-in `http`/`https`/`net` only) that
// lets https://blackeclipse reach the SAME server with no `:3000` in the URL:
//
//     browser  ->  https://blackeclipse (:443)  ->  this proxy (TLS terminated)
//                                               ->  http://127.0.0.1:3000 (next)
//
// It serves HTTPS when a locally-trusted certificate is present (provisioned by
// `npm run setup:tls`); otherwise it serves plain HTTP on :80 exactly as before.
// HTTPS makes the origin a SECURE CONTEXT, which the browser's desktop
// notification API requires (see docs/local-hostname.md).
//
// Design notes (why it is built this way):
//   * The Next.js server is NOT moved to a privileged port. It keeps running on
//     3000, so `npm run dev` / `next dev` / hot reload / API routes are
//     untouched; only the front door changes.
//   * The proxy listens on 127.0.0.1 ONLY, never 0.0.0.0 — the app stays on this
//     computer (a LAN machine cannot reach it even with the firewall off).
//   * The original `Host` header is preserved and X-Forwarded-* are added
//     (`x-forwarded-proto` reflects the public scheme), so Next.js reconstructs
//     `request.url` and the app's same-origin checks (api-guard) keep passing.
//   * WebSocket upgrades (Next dev HMR at /_next/webpack-hmr) are forwarded, so
//     hot module replacement works through the hostname.
//
// It is a LONG-LIVED front door, not a child of the app: stopping the app (or
// closing its tab) leaves this process running, and it answers with the branded
// `/offline` page instead of a refused connection. A per-user sign-in task keeps
// it available after a reboot (`black proxy on`). Stop it explicitly with
// Ctrl+C, `npm run proxy:stop`, or `black proxy off`.
//
// Config (all optional):
//   BE_PROXY_TLS         1/0 — allow TLS when a cert exists (default 1)
//   BE_PROXY_PORT         port to listen on (default 443 with TLS, else 80)
//   BE_PROXY_REDIRECT_PORT  http→https redirect port in TLS mode (default 80)
//   BE_PROXY_HOST         interface to bind     (default 127.0.0.1 — loopback)
//   BE_PROXY_TARGET       upstream origin       (default http://127.0.0.1:${PORT||3000})
//   PORT                  upstream port fallback (default 3000)

const http = require("http");
const https = require("https");
const net = require("net");
const path = require("path");
const { spawn } = require("child_process");
const { tlsConfig } = require("./lib/tls");
const { PROD } = require("./lib/profiles");
const { writeProxyState, clearProxyState } = require("./lib/proxy-state");
const { isNavigation, saveCachedPage, offlinePage } = require("./lib/proxy-offline");

const ROOT = path.join(__dirname, "..");

// TLS termination (optional). When a locally-trusted certificate is present
// (provisioned by `npm run setup:tls`) and BE_PROXY_TLS is not disabled, the
// proxy serves HTTPS so `https://blackeclipse` is a SECURE CONTEXT — required
// for the browser's desktop-notification API. Without a certificate it serves
// plain HTTP exactly as before (zero-config is preserved).
const TLS_ENABLED = !["0", "false", "no", "off", ""].includes(
  String(process.env.BE_PROXY_TLS || "1").trim().toLowerCase()
);
const tls = TLS_ENABLED ? tlsConfig() : null;
const USE_TLS = tls !== null;
const PUBLIC_PROTO = USE_TLS ? "https" : "http";

const LISTEN_PORT = parseInt(process.env.BE_PROXY_PORT || (USE_TLS ? "443" : "80"), 10);
const LISTEN_HOST = (process.env.BE_PROXY_HOST || "127.0.0.1").trim();
const REDIRECT_PORT = parseInt(process.env.BE_PROXY_REDIRECT_PORT || "80", 10);
const TARGET = new URL(
  // Default is the PRODUCTION app port, not 3000: the front door is started on
  // its own (at sign-in, and when the offline page asks for the app), with no
  // launcher environment to consult. The dev profile never uses a proxy.
  process.env.BE_PROXY_TARGET || `http://127.0.0.1:${PROD.appPort}`
);

const TARGET_HOST = TARGET.hostname;
const TARGET_PORT = parseInt(TARGET.port || (TARGET.protocol === "https:" ? "443" : "80"), 10);
const TARGET_ORIGIN = `${TARGET.protocol}//${TARGET.host}`;

function log(msg) {
  console.log(`[proxy] ${msg}`);
}

// Hop-by-hop headers must not be forwarded (RFC 7230 §6.1). `upgrade` is
// handled separately by the WebSocket path.
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function forwardedHeaders(req) {
  const headers = {};
  for (const [key, value] of Object.entries(req.headers)) {
    if (HOP_BY_HOP.has(key.toLowerCase())) continue;
    headers[key] = value;
  }
  // Preserve the caller's Host so Next.js sees the public origin the browser
  // used (blackeclipse), not the internal 127.0.0.1:3000.
  headers.host = req.headers.host;

  const remote = req.socket && req.socket.remoteAddress ? req.socket.remoteAddress : "";
  const prior = req.headers["x-forwarded-for"];
  headers["x-forwarded-for"] = prior ? `${prior}, ${remote}` : remote;
  headers["x-forwarded-host"] = req.headers.host;
  headers["x-forwarded-proto"] = PUBLIC_PROTO;
  return headers;
}

// ── The "app is offline" front door ─────────────────────────────────────────
//
// The proxy is the only process that can answer when the Next server is down, so
// it must answer with the branded page — never a refused connection or a bare
// 502. The page itself is rendered by the app (`/offline`, with the user's
// theme) and cached here; `lib/proxy-offline.js` owns the caching + fallback.

const CONTROL_PREFIX = "/__eclipse/";
let startingSince = 0;
let lastCacheRefresh = 0;

function sendJson(res, status, body) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(body));
}

function isLoopback(addr) {
  return !addr || addr === "127.0.0.1" || addr === "::1" || addr === "::ffff:127.0.0.1";
}

/** A control request must come from this origin (no cross-site form posts). */
function sameOrigin(req) {
  const origin = req.headers.origin;
  if (!origin) return true;
  try {
    return new URL(origin).host === String(req.headers.host || "");
  } catch {
    return false;
  }
}

/** One cheap request to the app; resolves true when anything answers. */
function upstreamAnswers(timeoutMs = 700) {
  return new Promise((resolve) => {
    const req = http.request(
      { protocol: TARGET.protocol, hostname: TARGET_HOST, port: TARGET_PORT, method: "GET", path: "/", timeout: timeoutMs },
      (res) => {
        res.resume();
        resolve((res.statusCode || 500) < 500);
      }
    );
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.on("error", () => resolve(false));
    req.end();
  });
}

/**
 * Pull a fresh copy of `/offline` from the app so the cached page follows the
 * user's theme. Throttled, best effort, and never awaited by a request.
 */
function refreshOfflinePage() {
  const now = Date.now();
  if (now - lastCacheRefresh < 5 * 60 * 1000) return;
  lastCacheRefresh = now;
  const req = http.request(
    {
      protocol: TARGET.protocol,
      hostname: TARGET_HOST,
      port: TARGET_PORT,
      method: "GET",
      path: "/offline",
      timeout: 4000,
      headers: {
        accept: "text/html",
        // Present the PUBLIC identity so the app's canonical-host middleware does
        // not answer with a 307 to the very host we are fetching from.
        host: process.env.BE_LOCAL_HOSTNAME || "blackeclipse",
        "x-forwarded-host": process.env.BE_LOCAL_HOSTNAME || "blackeclipse",
        "x-forwarded-proto": PUBLIC_PROTO,
      },
    },
    (res) => {
      if ((res.statusCode || 500) !== 200) {
        res.resume();
        return;
      }
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
        if (body.length > 600 * 1024) res.destroy();
      });
      res.on("end", () => saveCachedPage(body));
    }
  );
  req.on("timeout", () => req.destroy());
  req.on("error", () => {});
  req.end();
}

/** Boot the app on behalf of the offline page's button. */
function launchApp() {
  const now = Date.now();
  if (startingSince && now - startingSince < 45_000) return false;
  startingSince = now;
  try {
    const env = { ...process.env, BE_NO_PROXY: "1" };
    // Never inherit a stale control/proxy environment into the app launcher.
    delete env.BE_PROXY_TARGET;
    delete env.BE_PROXY_PORT;
    delete env.BE_PROXY_OWNER;
    const child = spawn(process.execPath, [path.join(ROOT, "scripts", "local-host.js"), "start"], {
      cwd: ROOT,
      env,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
    });
    child.unref();
    log("start requested from the offline page — booting the app");
    return true;
  } catch (err) {
    startingSince = 0;
    log(`could not start the app: ${err.message}`);
    return false;
  }
}

async function handleControl(req, res, route) {
  // Drain any body: the control surface never reads it, and an unread body can
  // hold the socket open.
  req.resume();
  if (!isLoopback(req.socket && req.socket.remoteAddress)) {
    sendJson(res, 403, { error: "loopback only" });
    return;
  }
  if (route === "/__eclipse/ping") {
    sendJson(res, 200, { ok: true, pid: process.pid, port: LISTEN_PORT, proto: PUBLIC_PROTO });
    return;
  }
  if (route === "/__eclipse/status") {
    sendJson(res, 200, {
      proxy: { pid: process.pid, port: LISTEN_PORT, proto: PUBLIC_PROTO, target: TARGET_ORIGIN },
      app: (await upstreamAnswers()) ? "up" : "down",
    });
    return;
  }
  if (route === "/__eclipse/start" && req.method === "POST") {
    // A cross-site page cannot set this header, and it must match this origin.
    if (req.headers["x-eclipse-control"] !== "1" || !sameOrigin(req)) {
      sendJson(res, 403, { error: "forbidden" });
      return;
    }
    const started = launchApp();
    sendJson(res, started ? 202 : 409, started ? { starting: true } : { starting: false });
    return;
  }
  sendJson(res, 404, { error: "not found" });
}

/** The branded page for a page load, or a small honest 503 for everything else. */
function serveUnavailable(req, res, err) {
  if (isNavigation(req)) {
    res.writeHead(200, {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "x-eclipse-offline": "1",
    });
    res.end(offlinePage());
    log(`app is down (${err.code || err.message}) — served the offline page`);
    return;
  }
  res.writeHead(503, {
    "content-type": "text/plain; charset=utf-8",
    "cache-control": "no-store",
    "retry-after": "3",
  });
  res.end(`BlackEclipse is not running (${err.code || err.message}).\nStart it with:  black eclipse\n`);
}

function handleRequest(req, res) {
  const route = String(req.url || "/").split("?")[0];
  if (route.startsWith(CONTROL_PREFIX)) {
    handleControl(req, res, route).catch(() => {
      if (!res.headersSent) sendJson(res, 500, { error: "control failure" });
    });
    return;
  }

  const upstream = http.request(
    {
      protocol: TARGET.protocol,
      hostname: TARGET_HOST,
      port: TARGET_PORT,
      method: req.method,
      path: req.url,
      headers: forwardedHeaders(req),
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
      upstreamRes.pipe(res);
      // The app answered a page: keep the offline copy in step with the theme.
      if ((upstreamRes.statusCode || 500) < 400 && isNavigation(req)) refreshOfflinePage();
    }
  );

  upstream.on("error", (err) => {
    if (res.headersSent) {
      res.destroy();
      return;
    }
    serveUnavailable(req, res, err);
  });

  req.pipe(upstream);
}

// The front door. HTTPS when a certificate is provisioned, plain HTTP otherwise.
// WebSocket/HMR upgrades are handled on both (an `https.Server` emits `upgrade`
// with an already-decrypted socket).
const server = USE_TLS
  ? https.createServer({ pfx: tls.pfx, passphrase: tls.passphrase }, handleRequest)
  : http.createServer(handleRequest);

// WebSocket / HMR upgrade: replay the raw request line + headers over a plain
// TCP socket and pipe both directions.
server.on("upgrade", (req, socket, head) => {
  const line = `${req.method} ${req.url} HTTP/1.1`;
  const headerLines = [];
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    const name = req.rawHeaders[i];
    const value = req.rawHeaders[i + 1];
    if (name.toLowerCase() === "host") {
      headerLines.push(`Host: ${req.headers.host}`);
    } else {
      headerLines.push(`${name}: ${value}`);
    }
  }
  const block = `${line}\r\n${headerLines.join("\r\n")}\r\n\r\n`;

  const upstream = net.connect(TARGET_PORT, TARGET_HOST, () => {
    upstream.write(block);
    if (head && head.length) upstream.write(head);
    upstream.pipe(socket);
    socket.pipe(upstream);
  });
  const fail = () => socket.destroy();
  upstream.on("error", fail);
  socket.on("error", fail);
});

server.on("clientError", (err, socket) => {
  if (socket.writable) socket.end("HTTP/1.1 400 Bad Request\r\n\r\n");
});

let listening = false;
// Replacing a door (settings changed, or one already running from an earlier
// launch) can take a moment to release the port. Retry briefly instead of
// failing the front door for the whole session.
let bindAttempts = 0;
const MAX_BIND_ATTEMPTS = 16;

server.on("error", (err) => {
  // Only listen-time failures are fatal. A transient server-level error after
  // the socket is open (e.g. a reset on a keep-alive connection) must NOT kill
  // the proxy and silently break every later request.
  if (!listening && err.code === "EADDRINUSE") {
    if (bindAttempts < MAX_BIND_ATTEMPTS) {
      bindAttempts += 1;
      setTimeout(() => server.listen(LISTEN_PORT, LISTEN_HOST), 250);
      return;
    }
    log(`port ${LISTEN_PORT} is already in use.`);
    log(`Find the owner:  Get-NetTCPConnection -LocalPort ${LISTEN_PORT} -State Listen`);
    log(`Stop it:         npm run proxy:stop`);
    process.exit(1);
  }
  if (!listening && err.code === "EACCES") {
    log(`permission denied binding ${LISTEN_HOST}:${LISTEN_PORT}.`);
    process.exit(1);
  }
  log(`non-fatal server error (continuing): ${err.message}`);
});

server.listen(LISTEN_PORT, LISTEN_HOST, () => {
  listening = true;
  // Announce the door to every launcher (`lib/proxy-state.js`): a later
  // `black eclipse` attaches to THIS process instead of starting a second one,
  // and the app stopping no longer takes the front door with it.
  writeProxyState({
    pid: process.pid,
    port: LISTEN_PORT,
    redirectPort: USE_TLS ? REDIRECT_PORT : null,
    tls: USE_TLS,
    proto: PUBLIC_PROTO,
    host: process.env.BE_LOCAL_HOSTNAME || "blackeclipse",
    target: TARGET_ORIGIN,
    startedAt: Date.now(),
  });
  log(`listening on ${PUBLIC_PROTO}://${process.env.BE_LOCAL_HOSTNAME || "blackeclipse"}  (${LISTEN_HOST}:${LISTEN_PORT})`);
  log(`forwarding to ${TARGET_ORIGIN}`);
  log(
    USE_TLS
      ? "TLS terminated here — https://blackeclipse is a secure context (desktop notifications available)."
      : "plain http (run `npm run setup:tls` to enable https and desktop notifications)."
  );
  log(`this machine only — not reachable from the local network.`);
  log(`stays up when the app stops and serves the branded offline page. Stop: npm run proxy:stop`);
  // Cache the themed offline page while the app is answering (best effort).
  refreshOfflinePage();
});

// When serving HTTPS, also answer plain HTTP on the redirect port and send the
// browser to the secure origin, so an old `http://blackeclipse` bookmark still
// lands somewhere useful. Best-effort: a conflict there is not fatal.
let redirectServer = null;
if (USE_TLS && REDIRECT_PORT !== LISTEN_PORT) {
  redirectServer = http.createServer((req, res) => {
    const host = (req.headers.host || "blackeclipse").replace(/:\d+$/, "");
    res.writeHead(301, { Location: `https://${host}${req.url}` });
    res.end();
  });
  redirectServer.on("error", (err) => {
    log(`http→https redirect disabled on :${REDIRECT_PORT} (${err.code || err.message}).`);
  });
  redirectServer.listen(REDIRECT_PORT, LISTEN_HOST, () => {
    log(`redirecting http://blackeclipse (${LISTEN_HOST}:${REDIRECT_PORT}) → https.`);
  });
}

function shutdown() {
  log("shutting down");
  clearProxyState(process.pid);
  if (redirectServer) {
    try {
      redirectServer.close();
    } catch {}
  }
  server.close(() => process.exit(0));
  // Don't hang on lingering keep-alive sockets.
  setTimeout(() => process.exit(0), 1000).unref();
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
process.on("exit", () => clearProxyState(process.pid));
