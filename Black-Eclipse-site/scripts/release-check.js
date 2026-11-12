#!/usr/bin/env node
/**
 * C9 release preflight: the three version fields must agree and the public API
 * must declare its surface version. Fails fast before a tag is created.
 */
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { root, pythonDir, resolvePython } = require("./python-runner");

const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const pyproject = fs.readFileSync(path.join(root, "pyproject.toml"), "utf8");
const pyVersion = (pyproject.match(/^version\s*=\s*"([^"]+)"/m) || [])[1];

const python = resolvePython();
if (!python) {
  console.error("[release] no Python interpreter with the harness dependencies is available");
  process.exit(2);
}
const probe = [
  "import sys",
  `sys.path.insert(0, ${JSON.stringify(pythonDir)})`,
  "import harness",
  "from harness.public import HARNESS_API_VERSION",
  "print(harness.__version__)",
  "print(HARNESS_API_VERSION)",
].join("; ");
const result = spawnSync(python, ["-c", probe], { cwd: root, encoding: "utf8" });
if ((result.status ?? 1) !== 0) {
  console.error(result.stderr || "[release] could not read harness.__version__");
  process.exit(2);
}
const [harnessVersion, apiVersion] = result.stdout.trim().split(/\r?\n/);
const problems = [];
if (!pyVersion) problems.push("pyproject.toml has no version");
if (pkg.version !== pyVersion) problems.push(`package.json ${pkg.version} != pyproject ${pyVersion}`);
if (harnessVersion !== pyVersion) problems.push(`harness.__version__ ${harnessVersion} != pyproject ${pyVersion}`);
if (!apiVersion) problems.push("harness.public.HARNESS_API_VERSION is missing");

for (const problem of problems) console.error(`[release] ${problem}`);
if (problems.length) process.exit(1);
console.log(`[release] versions agree: package ${pkg.version}, API ${apiVersion}`);
