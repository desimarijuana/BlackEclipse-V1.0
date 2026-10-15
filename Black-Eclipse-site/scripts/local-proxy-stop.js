#!/usr/bin/env node
// Stop the local hostname proxy — `npm run proxy:stop`.
//
// Finds whatever is listening on the proxy port (default 80) and terminates it.
// This is intentionally NOT a Windows service or scheduled task: the proxy is a
// plain foreground process you start and stop yourself.

const { execSync } = require("child_process");

const PORT = parseInt(process.env.BE_PROXY_PORT || "80", 10);

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

const pids = findListeners(PORT);
if (pids.size === 0) {
  console.log(`[proxy:stop] nothing is listening on port ${PORT}.`);
  process.exit(0);
}

for (const pid of pids) {
  console.log(`[proxy:stop] killing PID ${pid} on port ${PORT}...`);
  try {
    execSync(process.platform === "win32" ? `taskkill /F /PID ${pid}` : `kill -9 ${pid}`);
  } catch {
    console.warn(`[proxy:stop] could not kill PID ${pid} (already gone?)`);
  }
}
console.log(`[proxy:stop] port ${PORT} is free.`);
