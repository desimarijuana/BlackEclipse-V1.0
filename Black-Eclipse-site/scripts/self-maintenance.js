#!/usr/bin/env node
// Phase 22 / S3: the offline maintenance runner.
//
//   npm run self:maintenance -- plan    --preview <file>
//   npm run self:maintenance -- execute --preview <file> [--profile prod] [--allow-dirty]
//
// `plan` is read-only and safe. `execute` stops the app, applies an AUTHORITY
// change, runs the full gate, restarts, health-checks and rolls back on any
// failure. It is deliberately operator-run: the runtime must not hot-swap its
// own policy.
//
// This wrapper only resolves the vendored Python and forwards argv. The policy
// and the process control live in `python/harness/code/maintenance.py`, so there
// is ONE implementation of the order.

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");

function pythonExecutable() {
  if (process.env.BLACK_ECLIPSE_PYTHON) return process.env.BLACK_ECLIPSE_PYTHON;
  const vendored = path.join(
    ROOT, "scripts", "vendor", "python",
    process.platform === "win32" ? "python.exe" : path.join("bin", "python3"),
  );
  if (fs.existsSync(vendored)) return vendored;
  return process.platform === "win32" ? "python" : "python3";
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.log(
    "Usage:\n" +
    "  npm run self:maintenance -- plan    --preview <file>\n" +
    "  npm run self:maintenance -- execute --preview <file> [--profile prod|dev] [--allow-dirty] [--skip-tests]\n",
  );
  process.exit(0);
}

// The vendored Windows Python ignores PYTHONPATH, so insert the package path
// explicitly. The same snippet works for a normal interpreter.
const bootstrap =
  "import sys; sys.path.insert(0, 'python'); " +
  "from harness.code.maintenance import main; sys.exit(main(sys.argv[1:]))";

const result = spawnSync(pythonExecutable(), ["-c", bootstrap, ...args], {
  cwd: ROOT,
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: path.join(ROOT, "python") },
});

process.exit(typeof result.status === "number" ? result.status : 1);
