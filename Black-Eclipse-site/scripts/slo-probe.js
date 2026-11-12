#!/usr/bin/env node
/**
 * C7 SLO probe: run the deterministic telemetry workload and write
 * docs/harness/slo-report.json. The real release gate is `slo-gate.js`.
 */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const { root, pythonDir, resolvePython } = require("./python-runner");

const python = resolvePython();
if (!python) {
  console.error("[slo-probe] no Python interpreter with the harness dependencies is available");
  process.exit(2);
}

const script = path.join(pythonDir, "probe_slo.py");
const scriptArgs = [
  "--probe",
  "--out",
  path.join(root, "docs", "harness", "slo-report.json"),
  ...process.argv.slice(2),
];
// The vendored interpreter ships a `._pth` that disables cwd/PYTHONPATH
// insertion, so inject `python/` explicitly and run the CLI as __main__.
const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  `sys.argv = ${JSON.stringify([script, ...scriptArgs])}`,
  "import runpy",
  `runpy.run_path(${JSON.stringify(script)}, run_name="__main__")`,
].join("; ");

const result = spawnSync(python, ["-c", launcher], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env },
});

if (result.error) {
  console.error(`[slo-probe] ${result.error.message}`);
  process.exit(2);
}
process.exit(result.status ?? 1);
