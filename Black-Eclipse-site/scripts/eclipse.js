#!/usr/bin/env node
// Eclipse CLI launcher — `eclipse runtime|package|container|compose|deploy|k8s|terraform ...`
//
// The CLI itself is Python (harness/cli.py) because the agentic runtime is
// Python. This launcher finds the same interpreter the harness uses (the
// vendored one, then a system python) and runs `-m harness.cli`, forwarding every
// argument. It adds NO logic: it is only a cross-platform way to invoke it.
//
// Usage: node scripts/eclipse.js runtime inspect --root .
//    or (after `npm link` / install): eclipse runtime inspect --root .

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pythonDir = path.join(root, "python");
const vendored = path.join(__dirname, "vendor", "python", "python.exe");

function usable(cmd, isPath) {
  try {
    const check = spawnSync(cmd, ["--version"], { stdio: "ignore" });
    if (check.status !== 0) return false;
    return spawnSync(cmd, ["-c", "import langgraph, pytest"], { stdio: "ignore" }).status === 0;
  } catch {
    return false;
  }
}

const candidates =
  process.platform === "win32"
    ? [fs.existsSync(vendored) ? vendored : null, "python", "python3", "py"].filter(Boolean)
    : ["python3", "python"];

const isPath = (c) => c.includes(path.sep) || c.endsWith(".exe");
const py = candidates.find((c) => usable(c, isPath(c)));
if (!py) {
  console.error("[eclipse] The Python agent runtime is not installed. Run: npm run setup:python");
  process.exit(3);
}

// The vendored interpreter ships a `python312._pth` that disables implicit cwd
// insertion, so `-m harness.cli` cannot resolve the package from cwd alone.
const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.cli import main",
  "sys.exit(main(sys.argv[1:]))",
].join("; ");

const result = spawnSync(py, ["-c", launcher, ...process.argv.slice(2)], {
  stdio: "inherit",
  cwd: pythonDir,
  env: { ...process.env, PYTHONIOENCODING: "utf-8" },
});
process.exit(result.status == null ? 1 : result.status);
