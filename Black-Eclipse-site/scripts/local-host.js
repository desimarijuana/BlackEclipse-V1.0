#!/usr/bin/env node
// Profile launcher — the DEFAULT way to run BlackEclipse.
//
// Two independent profiles, so development and production can run at the same
// time without one killing the other (see `scripts/lib/profiles.js`):
//
//   node scripts/local-host.js dev     development: Next dev on 3000, no proxy,
//                                      harness 8765, isolated dev databases.
//   node scripts/local-host.js start   production: built Next on 3100 behind the
//                                      local proxy at http://blackeclipse,
//                                      harness 8766, the real databases.
//
// The proxy (scripts/local-proxy.js) is only part of production: it serves
// https://blackeclipse when a certificate exists (`npm run setup:tls`), making
// the origin a secure context so desktop notifications work.
//
// Next's own "Local: http://127.0.0.1:port" banner is rewritten to the advertised
// URL, so only that URL is shown. Ctrl+C stops the server (and the proxy).
//
// The raw server is still available when you want it: `npm run dev:next`
// (all interfaces) or `npm run dev:local` (loopback, no proxy).

const { spawn } = require("child_process");
const path = require("path");
const dns = require("dns");
const { nextBin } = require("./lib/server");
const { tlsAvailable } = require("./lib/tls");
const { profileFor, childEnv } = require("./lib/profiles");

const ROOT = path.join(__dirname, "..");
const APP_HOST = "127.0.0.1";
// TLS is used whenever a certificate is provisioned (`npm run setup:tls`) and
// the operator has not disabled it. This is what makes https://blackeclipse a
// secure context so desktop notifications work.
const TLS_DISABLED = ["0", "false", "no", "off"].includes(
  String(process.env.BE_PROXY_TLS || "").trim().toLowerCase()
);

function log(msg) {
  console.log(`[blackeclipse] ${msg}`);
}

function localName() {
  return (process.env.BE_LOCAL_HOSTNAME || "blackeclipse").trim();
}

// Warn (don't fail) when the hostname does not resolve to this machine yet.
function checkHostname(name) {
  dns.lookup(name, { all: true }, (err, addrs) => {
    const resolved =
      !err && Array.isArray(addrs) && addrs.some((a) => a.address === "127.0.0.1" || a.address === "::1");
    if (!resolved) {
      log(`warning: "${name}" does not resolve to 127.0.0.1 yet.`);
      log(`         Fix once with:  npm run setup:hostname`);
    }
  });
}

// Rewrite the internal 127.0.0.1:port URLs in the child's output so the only
// address shown is the advertised one.
function makeRewriter(port, shown) {
  const re = new RegExp(`https?://(?:127\\.0\\.0\\.1|localhost|\\[::1\\]):${port}`, "g");
  return (chunk) => chunk.toString().replace(re, shown);
}

function startProxy(appPort, { useTls, proxyPort }) {
  const child = spawn(process.execPath, [path.join(__dirname, "local-proxy.js")], {
    cwd: ROOT,
    env: {
      ...process.env,
      BE_PROXY_PORT: String(proxyPort),
      BE_PROXY_TLS: useTls ? "1" : "0",
      BE_PROXY_TARGET: `http://${APP_HOST}:${appPort}`,
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  let ready = false;
  child.stdout.on("data", (d) => {
    // Forward proxy output too: the desktop launcher captures this stream, and
    // a proxy that fails to bind must not disappear into a hidden console.
    process.stdout.write(d);
    if (d.toString().includes("listening")) ready = true;
  });
  child.stderr.on("data", (d) => process.stderr.write(d));
  child.on("exit", () => {
    if (!ready) {
      log(`proxy could not start on port ${proxyPort}.`);
      log(`  If a stale proxy is running:  npm run proxy:stop  (then restart)`);
      log(`  The app still runs directly on http://${APP_HOST}:${appPort}.`);
    }
  });
  return child;
}

function runProfile({ mode = "start", port } = {}) {
  const profile = profileFor(mode);
  const appPort = port || profile.appPort;
  const env = childEnv(profile);
  const name = localName();

  let proxy = null;
  let shown;
  let proto = "http";

  if (profile.proxy) {
    const useTls = !TLS_DISABLED && tlsAvailable(name);
    proto = useTls ? "https" : "http";
    shown = `${proto}://${name}`;
    const proxyPort = parseInt(process.env.BE_PROXY_PORT || (useTls ? "443" : "80"), 10);
    proxy = startProxy(appPort, { useTls, proxyPort });
    // One canonical origin for production, so every alias shares storage.
    if (env.BE_CANONICAL_HOST === undefined) env.BE_CANONICAL_HOST = name;
    process.on("exit", () => {
      try {
        proxy?.kill();
      } catch {}
    });
    process.on("SIGINT", () => {
      try {
        proxy?.kill();
      } catch {}
      process.exit(0);
    });
  } else {
    shown = `http://${APP_HOST}:${appPort}`;
  }

  const bar = "  " + "─".repeat(47);
  console.log("");
  console.log(bar);
  console.log(`    BlackEclipse  ${profile.label.padEnd(11)} ${shown}`);
  console.log(bar);
  console.log("");

  if (profile.proxy) {
    checkHostname(name);
    if (!TLS_DISABLED && !tlsAvailable(name) && process.platform === "win32") {
      log("tip: run `npm run setup:tls` once to serve https and enable desktop notifications.");
    }
  }

  const args = [
    nextBin(),
    profile.command,
    ...(profile.command === "dev" ? ["--turbopack"] : []),
    "-p",
    String(appPort),
    "-H",
    APP_HOST,
  ];
  const child = spawn(process.execPath, args, {
    cwd: ROOT,
    stdio: ["inherit", "pipe", "pipe"],
    env,
    windowsHide: true,
  });
  const rewrite = makeRewriter(appPort, shown);
  child.stdout.on("data", (d) => process.stdout.write(rewrite(d)));
  child.stderr.on("data", (d) => process.stderr.write(rewrite(d)));

  const cleanup = () => {
    try {
      proxy?.kill();
    } catch {}
  };
  process.on("SIGINT", () => {
    try {
      child.kill();
    } catch {}
    cleanup();
    process.exit(0);
  });
  process.on("SIGTERM", () => {
    try {
      child.kill();
    } catch {}
    cleanup();
    process.exit(0);
  });
  child.on("exit", (code) => {
    cleanup();
    process.exit(code ?? 0);
  });
}

// Backwards-compatible name for callers that imported `runLocalHost`.
function runLocalHost(options = {}) {
  runProfile(options);
}

if (require.main === module) {
  const mode = (process.argv[2] || "start").toLowerCase() === "dev" ? "dev" : "start";
  const i = process.argv.indexOf("-p");
  const port = i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : undefined;
  runProfile({ mode, port });
}

module.exports = { runProfile, runLocalHost };
