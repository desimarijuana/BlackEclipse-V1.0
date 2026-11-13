#!/usr/bin/env node
/**
 * W0 baseline collector wrapper.
 *
 * Runs the read-only Python collector with the same interpreter the harness
 * uses. It never starts a server and never writes the source database.
 *
 * Usage:
 *   node scripts/w0-baseline.js --db path/to/agent-memory.db \
 *     --out docs/harness/baselines/w0-<sha>-<date>.json [--label w0-baseline]
 *
 * Gate results (offline/live/SLO/audit) are collected separately; this command
 * records runtime metrics only, and marks anything it cannot measure UNKNOWN.
 */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const { root, pythonDir, resolvePython, pythonPathEnv } = require("./python-runner");

const py = resolvePython("import langgraph, pytest");
if (!py) {
  console.error("[w0-baseline] no Python interpreter with the harness dependencies is available");
  console.error("[w0-baseline] install it with: npm run setup:python");
  process.exit(2);
}

const argv = process.argv.slice(2);
const dbFlag = argv.indexOf("--db");
if (dbFlag < 0 || !argv[dbFlag + 1]) {
  console.error("[w0-baseline] --db <agent-memory.db> is required");
  process.exit(2);
}
if (!fs.existsSync(argv[dbFlag + 1])) {
  console.error(`[w0-baseline] database not found: ${argv[dbFlag + 1]}`);
  process.exit(2);
}
// The Python child runs with cwd=python/ so `import harness` works. Resolve
// user-supplied paths against the caller's cwd before spawning.
argv[dbFlag + 1] = path.resolve(argv[dbFlag + 1]);
const outFlag = argv.indexOf("--out");
if (outFlag >= 0 && argv[outFlag + 1]) {
  argv[outFlag + 1] = path.resolve(argv[outFlag + 1]);
}

const launcher = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "from harness.evaluation.w0_baseline import main",
  `sys.argv = ${JSON.stringify(["w0-baseline", ...argv])}`,
  "raise SystemExit(main())",
].join("; ");

const result = spawnSync(py, ["-c", launcher], {
  cwd: pythonDir,
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: pythonPathEnv() },
});

if (result.error) {
  console.error(`[w0-baseline] ${result.error.message}`);
  process.exit(2);
}
process.exit(result.status ?? 1);
