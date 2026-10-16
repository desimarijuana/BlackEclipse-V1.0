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
// It is intentionally not installed as a service or scheduled task. Start it in
// a terminal and stop it with Ctrl+C (or `npm run proxy:stop`).
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
const { tlsConfig } = require("./lib/tls");

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
  process.env.BE_PROXY_TARGET || `http://127.0.0.1:${process.env.PORT || "3000"}`
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

function handleRequest(req, res) {
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
    }
  );

  upstream.on("error", (err) => {
    if (res.headersSent) {
      res.destroy();
      return;
    }
    res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    res.end(
      `BlackEclipse proxy: upstream ${TARGET_ORIGIN} is not reachable (${err.code || err.message}).\n` +
        `Start the app first: npm run dev   (or  npm run up)\n`
    );
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

server.on("error", (err) => {
  // Only listen-time failures are fatal. A transient server-level error after
  // the socket is open (e.g. a reset on a keep-alive connection) must NOT kill
  // the proxy and silently break every later request.
  if (!listening && err.code === "EADDRINUSE") {
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
  log(`listening on ${PUBLIC_PROTO}://blackeclipse  (${LISTEN_HOST}:${LISTEN_PORT})`);
  log(`forwarding to ${TARGET_ORIGIN}`);
  log(
    USE_TLS
      ? "TLS terminated here — https://blackeclipse is a secure context (desktop notifications available)."
      : "plain http (run `npm run setup:tls` to enable https and desktop notifications)."
  );
  log(`this machine only — not reachable from the local network. Ctrl+C to stop.`);
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
