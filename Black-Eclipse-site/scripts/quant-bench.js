// Run QuantBench with the same interpreter the runtime uses.
// Skips (exit 0) when the agent stack is absent so `npm test` stays usable on a
// machine without the Python runtime; the TS suite still gates the app.
const { spawnSync } = require("child_process");
const path = require("path");
const { pythonDir, resolvePython } = require("./python-runner");

const py = resolvePython("import numpy, pydantic");
if (!py) {
  console.log("[quant-bench] Python agent stack not installed — skipping.");
  process.exit(0);
}

const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.quant_bench.__main__ import main",
  "sys.exit(main())",
].join("; ");

const result = spawnSync(py, ["-c", launcher], {
  stdio: "inherit",
  cwd: pythonDir,
  env: {
    ...process.env,
    PYTHONPATH: pythonDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
  },
});
process.exit(result.status ?? 1);
