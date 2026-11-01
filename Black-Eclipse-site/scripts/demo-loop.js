// ── Loop demo runner ─────────────────────────────────────────────────────────
// 1. builds the two IR documents with the REAL editor registry (dry run, no DB)
// 2. runs them through the REAL Python runtime (pinned body supplied like the
//    front door supplies it) and prints PASS/FAIL per behaviour.
//
//   npm run demo:loop
//
// Skips (exit 0) when the Python agent stack is absent, exactly like
// `demo:transform`. Use `npm run graph:loop` to create the workflows in JDDS.
const { spawnSync } = require("child_process");
const path = require("path");
const { root, pythonDir, resolvePython, pythonPathEnv } = require("./python-runner");

function fail(message) {
  console.error(`[loop-demo] ${message}`);
  process.exit(1);
}

const npx = process.platform === "win32" ? "npx.cmd" : "npx";
const build = spawnSync(npx, ["tsx", path.join("scripts", "graph-loop-demo.mts"), "--dry"], {
  stdio: "inherit",
  cwd: root,
  shell: process.platform === "win32",
});
if ((build.status ?? 1) !== 0) fail("the IR build failed");

const py = resolvePython("import pydantic");
if (!py) {
  console.log("[loop-demo] Python agent stack not installed — skipping the runtime check.");
  console.log("[loop-demo] Install it with: npm run setup:python");
  process.exit(0);
}

const run = spawnSync(py, [path.join(pythonDir, "examples", "loop_demo.py")], {
  stdio: "inherit",
  cwd: root,
  env: { ...process.env, PYTHONPATH: pythonPathEnv(), PYTHONIOENCODING: "utf-8" },
});
process.exit(run.status ?? 1);
