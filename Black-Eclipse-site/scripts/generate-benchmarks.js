#!/usr/bin/env node
/*
 * Regenerate the PUBLISHED benchmark file.
 *
 * Round 3 / W8 (ADR-H296). `docs/harness/benchmarks.md` is GENERATED - never
 * hand-edited - so a number cannot be quietly improved. This wrapper exists
 * because the vendored interpreter is ISOLATED (it ships a `python312._pth`,
 * so `PYTHONPATH` is ignored and `python -m harness...` cannot find the
 * package). It puts the package on `sys.path` explicitly and calls the same
 * `main()` the module exposes, so `python -m harness.evaluation.report` works
 * identically on a normal interpreter.
 *
 * Usage: node scripts/generate-benchmarks.js [--out <path>] [--live-run <id>]
 */

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

// These scripts live in `<site>/scripts/`, so `..` IS the site root.
const site = path.resolve(__dirname, "..");
const pythonDir = path.join(site, "python");

function interpreter() {
  const vendored = path.join(site, "scripts", "vendor", "python", "python.exe");
  if (fs.existsSync(vendored)) return vendored;
  return process.platform === "win32" ? "python" : "python3";
}

// A driver FILE, not `-c`: the paths on this machine contain spaces, and a
// shell re-parses a `-c` script on Windows.
const driver = path.join(os.tmpdir(), `eclipse-benchmarks-${process.pid}.py`);
fs.writeFileSync(
  driver,
  [
    "import sys",
    `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
    "from harness.evaluation.report import main",
    "raise SystemExit(main(sys.argv[1:]))",
    "",
  ].join("\n"),
  "utf8",
);

try {
  const result = spawnSync(interpreter(), [driver, ...process.argv.slice(2)], {
    stdio: "inherit",
    cwd: site,
  });
  process.exit(result.status ?? 1);
} finally {
  try { fs.unlinkSync(driver); } catch (_) { /* best effort */ }
}
