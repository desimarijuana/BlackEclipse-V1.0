#!/usr/bin/env node
/**
 * C8 conformance gate. Runs the fault matrix, golden trace and contract checks
 * through the shipped harness. Offline and deterministic.
 *
 * Usage: node scripts/conformance-gate.js [--quick] [--only id] [--json path]
 */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const { root, pythonDir, resolvePython } = require("./python-runner");

const python = resolvePython();
if (!python) {
  console.error("[conformance] no Python interpreter with the harness dependencies is available");
  process.exit(2);
}

const args = ["--json", path.join(root, "docs", "harness", "conformance-report.json"), ...process.argv.slice(2)];
const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  `sys.argv = ${JSON.stringify(["harness.evaluation.conformance", ...args])}`,
  "import runpy",
  `runpy.run_module("harness.evaluation.conformance", run_name="__main__")`,
].join("; ");

const result = spawnSync(python, ["-c", launcher], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env },
});
if (result.error) {
  console.error(`[conformance] ${result.error.message}`);
  process.exit(2);
}
process.exit(result.status ?? 1);
