#!/usr/bin/env node
/**
 * C8.5: regenerate docs/harness/scorecard.json from a real evaluation run and
 * the C7 release report, then regenerate the markdown. No typed metrics.
 */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const { root, pythonDir, resolvePython } = require("./python-runner");

const python = resolvePython();
if (!python) {
  console.error("[scorecard] no Python interpreter with the harness dependencies is available");
  process.exit(2);
}

const script = path.join(pythonDir, "scorecard_from_runs.py");
const args = [...process.argv.slice(2)];
const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  `sys.argv = ${JSON.stringify([script, ...args])}`,
  "import runpy",
  `runpy.run_path(${JSON.stringify(script)}, run_name="__main__")`,
].join("; ");

const generate = spawnSync(python, ["-c", launcher], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env },
});
if (generate.error || (generate.status ?? 1) !== 0) {
  console.error("[scorecard] generation failed");
  process.exit(generate.status ?? 2);
}

const render = spawnSync(process.execPath, [path.join(root, "scripts", "harness-scorecard.js")], {
  cwd: root,
  stdio: "inherit",
});
process.exit(render.status ?? 1);
