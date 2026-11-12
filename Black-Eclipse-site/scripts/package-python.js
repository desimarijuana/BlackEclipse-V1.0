#!/usr/bin/env node
/** C9: build the Python wheel/sdist from pyproject.toml. */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const { root, resolvePython } = require("./python-runner");

const python = resolvePython();
if (!python) {
  console.error("[package] no Python interpreter with the harness dependencies is available");
  process.exit(2);
}
const args = ["-m", "build", "--outdir", path.join(root, "dist")];
let result = spawnSync(python, args, { cwd: root, stdio: "inherit", env: { ...process.env } });
if (result.error || (result.status ?? 1) !== 0) {
  // `build` is optional; pip can build the same wheel from pyproject.toml.
  console.log("[package] `build` unavailable; falling back to pip wheel");
  const candidates = [python, process.env.PYTHON, "python", "python3"].filter(Boolean);
  for (const candidate of candidates) {
    result = spawnSync(candidate, ["-m", "pip", "wheel", ".", "--no-deps", "-w", path.join(root, "dist")],
      { cwd: root, stdio: "inherit", env: { ...process.env } });
    if (!result.error && (result.status ?? 1) === 0) break;
  }
}
if (result.error || (result.status ?? 1) !== 0) {
  console.error("[package] wheel build failed");
  process.exit(result.status ?? 2);
}
process.exit(0);
