#!/usr/bin/env node
// Stop the local hostname front door — `npm run proxy:stop` / `black proxy off`.
//
// Finds whatever is listening on the front door's port(s) and terminates it. In
// TLS mode it serves HTTPS on :443 AND an http→https redirect on :80, so both
// are stopped; in plain-http mode only :80.
//
// This is the ONLY way the door is stopped: launchers no longer kill it when the
// app exits, because keeping it up is what shows the branded offline page
// instead of a refused connection. `black proxy off` also removes the per-user
// sign-in task so it does not come back at the next login.

const { execSync } = require("child_process");
const { tlsAvailable } = require("./lib/tls");
const { readProxyState, clearProxyState } = require("./lib/proxy-state");

const TLS_DISABLED = ["0", "false", "no", "off"].includes(
  String(process.env.BE_PROXY_TLS || "").trim().toLowerCase()
);
const useTls = !TLS_DISABLED && tlsAvailable();

const ports = new Set();
ports.add(parseInt(process.env.BE_PROXY_PORT || (useTls ? "443" : "80"), 10));
if (useTls) ports.add(parseInt(process.env.BE_PROXY_REDIRECT_PORT || "80", 10));

function findListeners(port) {
  const pids = new Set();
  if (process.platform === "win32") {
    const output = execSync("netstat -ano", { encoding: "utf8" });
    for (const line of output.split(/\r?\n/)) {
      if (line.includes(`:${port} `) && line.includes("LISTENING")) {
        const pid = line.trim().split(/\s+/).pop();
        if (pid && pid !== "0") pids.add(pid);
      }
    }
  } else {
    try {
      const out = execSync(`lsof -t -i:${port} -sTCP:LISTEN`, { encoding: "utf8" });
      for (const pid of out.split(/\s+/)) if (pid) pids.add(pid);
    } catch {
      /* not in use */
    }
  }
  return pids;
}

let any = false;
for (const port of ports) {
  const pids = findListeners(port);
  if (pids.size === 0) {
    console.log(`[proxy:stop] nothing is listening on port ${port}.`);
    continue;
  }
  for (const pid of pids) {
    any = true;
    console.log(`[proxy:stop] killing PID ${pid} on port ${port}...`);
    try {
      execSync(process.platform === "win32" ? `taskkill /F /PID ${pid}` : `kill -9 ${pid}`);
    } catch {
      console.warn(`[proxy:stop] could not kill PID ${pid} (already gone?)`);
    }
  }
}
const state = readProxyState();
if (state) clearProxyState(state.pid);
if (any) console.log(`[proxy:stop] stopped.`);
