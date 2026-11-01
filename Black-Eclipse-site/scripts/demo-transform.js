// ── Transform-node demo runner ───────────────────────────────────────────────
// Runs `python/examples/transform_demo.py` with the SAME interpreter the runtime
// uses, so what you see is what a graph run would do. Skips (exit 0) when the
// Python agent stack is absent, exactly like the test runner.
//
//   npm run demo:transform
//   node scripts/demo-transform.js
const { spawnSync } = require("child_process");
const path = require("path");
const { root, pythonDir, resolvePython, pythonPathEnv } = require("./python-runner");

const py = resolvePython("import pydantic");
if (!py) {
  console.log("[demo] Python agent stack not installed — skipping.");
  console.log("[demo] Install it with: npm run setup:python");
  process.exit(0);
}

const result = spawnSync(py, [path.join(pythonDir, "examples", "transform_demo.py")], {
  stdio: "inherit",
  cwd: root,
  env: { ...process.env, PYTHONPATH: pythonPathEnv() },
});
process.exit(result.status ?? 1);
