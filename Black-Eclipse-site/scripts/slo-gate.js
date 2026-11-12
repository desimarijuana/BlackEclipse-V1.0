#!/usr/bin/env node
/**
 * C7 release gate. Runs the deterministic probe through the shipped
 * observability path, then fails when a budget or a committed regression
 * allowance is exceeded.
 *
 * Usage: node scripts/slo-gate.js [--runs N] [--report path] [--no-probe]
 */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const { root, pythonDir, resolvePython } = require("./python-runner");

const python = resolvePython();
if (!python) {
  console.error("[slo-gate] no Python interpreter with the harness dependencies is available");
  process.exit(2);
}

const argv = process.argv.slice(2);
const script = path.join(pythonDir, "probe_slo.py");
const args = ["--gate"];
// Default: probe + gate, writing the report the release artifacts keep.
const reportFlag = argv.indexOf("--report");
const noProbe = argv.includes("--no-probe");
if (reportFlag >= 0 && argv[reportFlag + 1]) {
  args.push("--report", argv[reportFlag + 1]);
} else if (!noProbe) {
  args.push("--write-report", path.join(root, "docs", "harness", "slo-report.json"));
}
for (let i = 0; i < argv.length; i += 1) {
  if (argv[i] === "--no-probe") continue;
  if (argv[i] === "--report") {
    i += 1;
    continue;
  }
  args.push(argv[i]);
}

const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  `sys.argv = ${JSON.stringify([script, ...args])}`,
  "import runpy",
  `runpy.run_path(${JSON.stringify(script)}, run_name="__main__")`,
].join("; ");

const result = spawnSync(python, ["-c", launcher], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env },
});

if (result.error) {
  console.error(`[slo-gate] ${result.error.message}`);
  process.exit(2);
}
process.exit(result.status ?? 1);
