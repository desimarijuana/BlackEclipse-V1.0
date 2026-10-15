#!/usr/bin/env node
// Local hostname launcher — the DEFAULT way to run BlackEclipse.
//
// Starts BOTH processes together so `http://blackeclipse` is the only URL you
// need, with no `:3000`:
//
//   1. the Next.js server, bound to 127.0.0.1 (never exposed to the LAN), and
//   2. the local reverse proxy (scripts/local-proxy.js) on 127.0.0.1:80.
//
// Next's own "Local: http://127.0.0.1:3000" banner is rewritten on the fly to
// the hostname, so only `http://blackeclipse` is shown. Ctrl+C stops both.
//
//   npm run dev                     -> dev mode (hot reload)
//   node scripts/local-host.js dev
//   node scripts/local-host.js start -> production serve (needs a build first)
//
// The raw server is still available when you want it: `npm run dev:next`
// (all interfaces) or `npm run dev:local` (loopback, no proxy).

const { spawn } = require("child_process");
const path = require("path");
const dns = require("dns");
const { nextBin } = require("./lib/server");

const ROOT = path.join(__dirname, "..");
const APP_HOST = "127.0.0.1";
const PROXY_PORT = parseInt(process.env.BE_PROXY_PORT || "80", 10);

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
// address shown is the hostname.
function makeRewriter(port, name) {
  const re = new RegExp(`https?://(?:127\\.0\\.0\\.1|localhost|\\[::1\\]):${port}`, "g");
  return (chunk) => chunk.toString().replace(re, `http://${name}`);
}

function startProxy(appPort) {
  const child = spawn(process.execPath, [path.join(__dirname, "local-proxy.js")], {
    cwd: ROOT,
    env: {
      ...process.env,
      BE_PROXY_PORT: String(PROXY_PORT),
      BE_PROXY_TARGET: `http://${APP_HOST}:${appPort}`,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let ready = false;
  child.stdout.on("data", (d) => {
    if (d.toString().includes("listening")) ready = true;
  });
  child.stderr.on("data", (d) => process.stderr.write(d));
  child.on("exit", () => {
    if (!ready) {
      log(`proxy could not start on port ${PROXY_PORT}.`);
      log(`  If a stale proxy is running:  npm run proxy:stop  (then restart)`);
      log(`  The app still runs directly on http://${APP_HOST}:${appPort}.`);
    }
  });
  return child;
}

function runLocalHost({ mode = "dev", port = process.env.PORT || "3000" } = {}) {
  const name = localName();
  const proxy = startProxy(port);

  console.log("");
  console.log("  ──────────────────────────────────────────────");
  console.log(`    BlackEclipse  →   http://${name}`);
  console.log("  ──────────────────────────────────────────────");
  console.log("");
  checkHostname(name);

  const args = [nextBin(), mode === "start" ? "start" : "dev", "-p", String(port), "-H", APP_HOST];
  const child = spawn(process.execPath, args, {
    cwd: ROOT,
    stdio: ["inherit", "pipe", "pipe"],
    env: process.env,
  });
  const rewrite = makeRewriter(port, name);
  child.stdout.on("data", (d) => process.stdout.write(rewrite(d)));
  child.stderr.on("data", (d) => process.stderr.write(rewrite(d)));

  const cleanup = () => {
    try {
      proxy.kill();
    } catch {}
  };
  process.on("exit", cleanup);
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
  child.on("exit", (code) => process.exit(code ?? 0));
}

if (require.main === module) {
  const mode = (process.argv[2] || "dev").toLowerCase() === "start" ? "start" : "dev";
  const i = process.argv.indexOf("-p");
  const port = i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : process.env.PORT || "3000";
  runLocalHost({ mode, port });
}

module.exports = { runLocalHost };
