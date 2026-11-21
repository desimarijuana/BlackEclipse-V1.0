// Regenerate (or check) the broker capability matrix in docs/trading.md.
//
// The declarations live in Python (`harness/trade/registry.py`), so this is a
// thin wrapper over the project's runtime interpreter rather than a second
// implementation in JS. `--check` is the CI form: it exits 1 when the committed
// page disagrees with the code.
const { spawnSync } = require("child_process");
const { resolvePython, pythonPathEnv, pythonDir } = require("./python-runner");

const check = process.argv.includes("--check");
const py = resolvePython("import pydantic");
if (!py) {
  console.error("[docs:brokers] Python agent stack not installed — run `npm run setup:python`.");
  process.exit(1);
}

// The vendored interpreter ships a `_pth` that disables implicit sys.path[0]
// insertion, so `-m harness.*` cannot resolve from cwd alone (same constraint
// scripts/test-python.js documents). Import the module explicitly instead.
const body = `
import sys
sys.path.insert(0, ${JSON.stringify(pythonDir)})
from harness.trade.capability_matrix import main
raise SystemExit(main([${JSON.stringify(check ? "--check" : "--write")}]))
`;

const result = spawnSync(py, ["-c", body], {
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: pythonPathEnv() },
});
process.exit(result.status === null ? 1 : result.status);
