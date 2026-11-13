#!/usr/bin/env node
/**
 * W0 lifecycle soak wrapper. Runs the real graph loop with a scripted model on
 * a private temp DB, then writes the baseline JSON + Markdown.
 *
 * Usage:
 *   node scripts/w0-soak.js --out docs/harness/baselines/w0-<sha>-<date>.json \
 *     [--sequential 50] [--concurrent 24] [--gates gates.json]
 */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const { pythonDir, resolvePython, pythonPathEnv } = require("./python-runner");

const py = resolvePython("import langgraph, pytest");
if (!py) {
  console.error("[w0-soak] no Python interpreter with the harness dependencies is available");
  process.exit(2);
}

const argv = process.argv.slice(2);
const outFlag = argv.indexOf("--out");
if (outFlag < 0 || !argv[outFlag + 1]) {
  console.error("[w0-soak] --out <baseline.json> is required");
  process.exit(2);
}
argv[outFlag + 1] = path.resolve(argv[outFlag + 1]);
const gatesFlag = argv.indexOf("--gates");
if (gatesFlag >= 0 && argv[gatesFlag + 1]) {
  argv[gatesFlag + 1] = path.resolve(argv[gatesFlag + 1]);
}

const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.evaluation.w0_soak import main",
  `sys.argv = ${JSON.stringify(["w0-soak", ...argv])}`,
  "raise SystemExit(main())",
].join("; ");

const result = spawnSync(py, ["-c", launcher], {
  cwd: pythonDir,
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: pythonPathEnv() },
});
if (result.error) {
  console.error(`[w0-soak] ${result.error.message}`);
  process.exit(2);
}
process.exit(result.status ?? 1);
