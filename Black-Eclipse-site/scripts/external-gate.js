#!/usr/bin/env node
/** C8.2 external-adapter gate over the committed offline fixtures. */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const { root, pythonDir, resolvePython } = require("./python-runner");

const python = resolvePython();
if (!python) {
  console.error("[external] no Python interpreter with the harness dependencies is available");
  process.exit(2);
}

const args = ["--gate", "--json", path.join(root, "docs", "harness", "external-report.json"),
  ...process.argv.slice(2)];
const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  `sys.argv = ${JSON.stringify(["harness.evaluation.adapters", ...args])}`,
  "import runpy",
  `runpy.run_module("harness.evaluation.adapters", run_name="__main__")`,
].join("; ");

const result = spawnSync(python, ["-c", launcher], {
  cwd: root, stdio: "inherit", env: { ...process.env },
});
if (result.error) {
  console.error(`[external] ${result.error.message}`);
  process.exit(2);
}
process.exit(result.status ?? 1);
