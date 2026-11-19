#!/usr/bin/env node
// Provision a relocatable Python for macOS and Linux.
//
// Windows already has `setup-embedded-python.js` (the official embeddable zip).
// macOS and Linux have no equivalent, so this uses python-build-standalone
// (astral-sh), which ships a self-contained, relocatable CPython per target.
//
// Why not the system python: the payload must work on a machine that has no
// Python installed at all. `sys.executable` from the builder is the wrong answer.
//
//   node scripts/setup-portable-python.js          # into scripts/vendor/python
//   node scripts/setup-portable-python.js --check  # exit 0 if usable
//
// Windows is deliberately not handled here — changing a working embed flow would
// risk the shipped Windows build for no gain.

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const VENDOR = path.join(ROOT, "scripts", "vendor", "python");
const CACHE = path.join(ROOT, ".black-eclipse", "python-cache");
// Records which requirements produced this interpreter's dependency stack.
// Without it every run reinstalled the whole stack, so a restored CI cache of
// the runtime still paid the full pip install.
const MARKER = path.join(VENDOR, ".ready");

// Pinned on purpose: a floating "latest" would make two builds of the same commit
// ship different interpreters.
const PBS_RELEASE = "20241016";
const PY_VERSION = "3.12.7";

function targetTriple() {
  const arch = process.arch === "arm64" ? "aarch64" : "x86_64";
  if (process.platform === "darwin") return `${arch}-apple-darwin`;
  if (process.platform === "linux") return `${arch}-unknown-linux-gnu`;
  return null;
}

function pythonBin() {
  return process.platform === "win32"
    ? path.join(VENDOR, "python.exe")
    : path.join(VENDOR, "bin", "python3");
}

function usable() {
  const bin = pythonBin();
  if (!fs.existsSync(bin)) return false;
  const r = spawnSync(bin, ["-c", "import sys; print(sys.version_info[:2])"], { encoding: "utf8" });
  return r.status === 0 && r.stdout.includes("(3, 12)");
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: "inherit", ...opts });
  if (r.status !== 0) throw new Error(`${cmd} failed (exit ${r.status})`);
}

// Identifies the dependency set, not the interpreter: the requirement files are
// the only inputs to the pip install below.
function requirementsDigest() {
  const hash = crypto.createHash("sha256");
  for (const rel of ["python/requirements.txt", "python/analysis-requirements.txt"]) {
    const file = path.join(ROOT, rel);
    hash.update(rel);
    try {
      hash.update(fs.readFileSync(file));
    } catch {
      hash.update("missing");
    }
  }
  return hash.digest("hex").slice(0, 16);
}

function dependenciesCurrent() {
  try {
    return fs.readFileSync(MARKER, "utf8").trim() === requirementsDigest();
  } catch {
    return false;
  }
}

if (process.argv.includes("--check")) {
  process.exit(usable() ? 0 : 1);
}

if (process.platform === "win32") {
  console.log("[python] Windows uses setup-embedded-python.js — nothing to do here.");
  process.exit(0);
}

const triple = targetTriple();
if (!triple) {
  console.error(`[python] unsupported platform ${process.platform}/${process.arch}`);
  process.exit(1);
}

if (usable()) {
  console.log(`[python] vendored runtime already present at ${path.relative(ROOT, VENDOR)}`);
} else {
  const name = `cpython-${PY_VERSION}+${PBS_RELEASE}-${triple}-install_only`;
  const archive = path.join(CACHE, `${name}.tar.gz`);
  const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${name}.tar.gz`;

  fs.mkdirSync(CACHE, { recursive: true });
  if (!fs.existsSync(archive)) {
    console.log(`[python] downloading ${name}.tar.gz`);
    run("curl", ["-fsSL", "--retry", "3", "-o", archive, url]);
  }

  const extract = path.join(CACHE, name);
  fs.rmSync(extract, { recursive: true, force: true });
  fs.mkdirSync(extract, { recursive: true });
  run("tar", ["-xzf", archive, "-C", extract]);

  // The archive contains a single `python/` directory.
  const inner = path.join(extract, "python");
  if (!fs.existsSync(inner)) throw new Error(`unexpected archive layout in ${name}`);

  fs.rmSync(VENDOR, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(VENDOR), { recursive: true });
  fs.cpSync(inner, VENDOR, { recursive: true });
  console.log(`[python] installed ${PY_VERSION} into ${path.relative(ROOT, VENDOR)}`);
}

// Dependencies, installed into the vendored interpreter (never the system one).
const requirements = path.join(ROOT, "python", "requirements.txt");
if (fs.existsSync(requirements)) {
  if (dependenciesCurrent()) {
    console.log("[python] dependency stack is already current — skipping pip install");
  } else {
    const bin = pythonBin();
    run(bin, ["-m", "ensurepip", "--upgrade"]);
    run(bin, ["-m", "pip", "install", "--no-warn-script-location", "-r", requirements]);
    const analysis = path.join(ROOT, "python", "analysis-requirements.txt");
    if (fs.existsSync(analysis)) {
      run(bin, ["-m", "pip", "install", "--no-warn-script-location", "-r", analysis]);
    }
  }
  if (!dependenciesCurrent()) {
    fs.writeFileSync(MARKER, `${requirementsDigest()}\n`);
  }
}

if (!usable()) {
  console.error("[python] provisioning finished but the interpreter is not usable");
  process.exit(1);
}
console.log(`[python] ready: ${pythonBin()}`);
