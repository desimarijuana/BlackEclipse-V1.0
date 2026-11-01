// ── Python interpreter discovery ────────────────────────────────────────────
// ONE place answers "which python is the runtime?": the vendored interpreter
// when the agent stack was installed, otherwise a system python that can import
// the harness dependencies. `test-python.js` and `demo-transform.js` must agree,
// or a demo would prove something the test suite never runs.
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pythonDir = path.join(root, "python");
const vendored = path.join(__dirname, "vendor", "python", "python.exe");

function tryRun(cmd, args, opts = {}) {
  try {
    return spawnSync(cmd, args, { stdio: "ignore", ...opts });
  } catch {
    return { status: 1 };
  }
}

function candidates() {
  return process.platform === "win32"
    ? [fs.existsSync(vendored) ? vendored : null, "python", "python3", "py"].filter(Boolean)
    : ["python3", "python"];
}

/**
 * The first interpreter that runs `probe` successfully, or null.
 * `probe` is a `python -c` body, e.g. "import langgraph, pytest".
 */
function resolvePython(probe = "import pydantic") {
  for (const cmd of candidates()) {
    if (tryRun(cmd, ["--version"]).status !== 0) continue;
    if (tryRun(cmd, ["-c", probe]).status !== 0) continue;
    return cmd;
  }
  return null;
}

/** PYTHONPATH that makes `import harness` work for either interpreter. */
function pythonPathEnv(base = process.env) {
  return pythonDir + (base.PYTHONPATH ? path.delimiter + base.PYTHONPATH : "");
}

module.exports = { root, pythonDir, resolvePython, pythonPathEnv };
