#!/usr/bin/env node
// `npm run release:build` — produce the artifact the updater actually ships.
//
// The updater no longer checks out a tag and compiles on the user's machine
// (every release touches the changelog, so a dirty tree blocked the update).
// Instead the release publishes its COMPILED `.next` as a zip, the manifest
// signs its sha256/size/BUILD_ID, and the client promotes those bytes.
//
// This script:
//   1. makes sure `.next` is a completed build of the current source,
//   2. copies the runtime-only subset (Next's cache/diagnostics/trace/standalone
//      are dropped) into a staging dir,
//   3. zips it as dist/BlackEclipse-Build-<version>.zip,
//   4. prints the exact values `update-sign.js --build-*` needs.
//
// Usage: node scripts/release-build-zip.js [--no-build]

"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const { build, needsBuild } = require("./lib/server");
const { copyRuntime, buildLooksComplete, readBuildId } = require("./lib/desktop-release");
const { sha256File, lockHash } = require("./lib/build-artifact");

const noBuild = process.argv.includes("--no-build");
const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));

function log(message) {
  console.log(`[release:build] ${message}`);
}

function fail(message) {
  console.error(`[release:build] ${message}`);
  process.exit(1);
}

const DIST = path.join(ROOT, ".next");
const STAGE = path.join(ROOT, ".runtime", "release-build");
const OUT_DIR = path.join(ROOT, "dist");

if (!noBuild && needsBuild()) {
  log("building the production bundle (slow)…");
  try {
    build();
  } catch (err) {
    fail(`build failed: ${err && err.message ? err.message : err}`);
  }
}

if (!buildLooksComplete(DIST)) {
  fail("no completed .next build. Run `npm run build` (or drop --no-build) first.");
}

const buildId = readBuildId(DIST);
const version = pkg.version;

log(`staging the runtime build ${buildId}…`);
fs.rmSync(STAGE, { recursive: true, force: true });
fs.mkdirSync(STAGE, { recursive: true });
copyRuntime(DIST, path.join(STAGE, ".next"));
if (!buildLooksComplete(path.join(STAGE, ".next"))) {
  fail("the staged copy is not a serviceable build (validation failed)");
}

fs.mkdirSync(OUT_DIR, { recursive: true });
const outFile = path.join(OUT_DIR, `BlackEclipse-Build-${version}.zip`);
fs.rmSync(outFile, { force: true });

// `tar -a` writes a zip through bsdtar (Windows 10+, macOS). GNU tar cannot, so
// Linux prefers `zip`.
const args = ["-a", "-c", "-f", outFile, "-C", STAGE, "."];
const attempts =
  process.platform === "win32"
    ? [["tar", args], ["zip", ["-qr", outFile, "."]]]
    : [["zip", ["-qr", outFile, "."]], ["tar", args]];
let archived = false;
for (const [tool, toolArgs] of attempts) {
  const cwd = tool === "zip" ? STAGE : undefined;
  const result = spawnSync(tool, toolArgs, { cwd, stdio: "inherit", windowsHide: true });
  if (result.status === 0 && fs.existsSync(outFile)) {
    archived = tool;
    break;
  }
}
if (!archived) fail("could not create the zip: neither `zip` nor a zip-capable `tar` is available.");

fs.rmSync(STAGE, { recursive: true, force: true });

const digest = sha256File(outFile);
const size = fs.statSync(outFile).size;
const lock = lockHash(ROOT);

log(`archive ${path.relative(ROOT, outFile)} (${(size / (1024 * 1024)).toFixed(0)} MB, via ${archived})`);
console.log("");
console.log("Sign the manifest with:");
console.log(
  `  node scripts/update-sign.js --version ${version} --channel stable --commit <tag-sha> \\\n` +
    `    --build-file "${path.relative(ROOT, outFile)}" \\\n` +
    `    --build-url https://github.com/<owner>/<repo>/releases/download/v${version}/BlackEclipse-Build-${version}.zip \\\n` +
    `    --build-id ${buildId} --build-lock-hash ${lock || "<none>"}`,
);
console.log("");
console.log(`buildId   ${buildId}`);
console.log(`sha256    ${digest}`);
console.log(`size      ${size}`);
console.log(`lockHash  ${lock || "<none>"}`);
