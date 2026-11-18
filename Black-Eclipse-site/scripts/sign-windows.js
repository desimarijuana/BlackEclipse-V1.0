#!/usr/bin/env node
// Sign Windows binaries with `signtool` — but only when certificate material is
// configured.
//
// The whole point is that a release is READY to be signed: adding the secret is
// the only step left. Without one, every path still builds and the build log
// says plainly that the binaries are unsigned (SmartScreen will warn).
//
// Configure ONE of:
//   WINDOWS_CERT_PFX_BASE64 + WINDOWS_CERT_PASSWORD   CI / no local cert store
//   WINDOWS_CERT_THUMBPRINT                           cert already installed
// Optional:
//   SIGNTOOL_PATH          explicit signtool.exe
//   WINDOWS_TIMESTAMP_URL  default http://timestamp.digicert.com
//
// Usage:
//   node scripts/sign-windows.js --check              report configuration only
//   node scripts/sign-windows.js <file> [<file>...]   sign each file
//
// Exit codes: 0 = signed or deliberately skipped, 1 = configured but failed,
// 2 = bad usage.

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const TIMESTAMP_URL = process.env.WINDOWS_TIMESTAMP_URL || "http://timestamp.digicert.com";

function pfxBase64() {
  const value = (process.env.WINDOWS_CERT_PFX_BASE64 || "").trim();
  return value || null;
}

function thumbprint() {
  const value = (process.env.WINDOWS_CERT_THUMBPRINT || "").replace(/[\s:]/g, "");
  return value || null;
}

function isConfigured() {
  return Boolean(pfxBase64() || thumbprint());
}

/** Why signing is (or is not) available, in one line — printed by the builds. */
function describe() {
  if (process.platform !== "win32") return "not Windows";
  if (pfxBase64()) return "configured (PFX)";
  if (thumbprint()) return "configured (certificate store)";
  return "not configured — unsigned build, Windows SmartScreen will warn";
}

/** Newest Windows-Kits signtool, or null. */
function findSigntool() {
  if (process.env.SIGNTOOL_PATH && fs.existsSync(process.env.SIGNTOOL_PATH)) {
    return process.env.SIGNTOOL_PATH;
  }
  const roots = [
    process.env["ProgramFiles(x86)"],
    process.env.ProgramFiles,
  ].filter(Boolean);
  let best = null;
  let bestVersion = "";
  for (const root of roots) {
    const kits = path.join(root, "Windows Kits", "10", "bin");
    let versions = [];
    try {
      versions = fs.readdirSync(kits);
    } catch {
      continue;
    }
    for (const version of versions) {
      const candidate = path.join(kits, version, "x64", "signtool.exe");
      if (fs.existsSync(candidate) && version > bestVersion) {
        best = candidate;
        bestVersion = version;
      }
    }
  }
  if (best) return best;
  // A signtool on PATH (SDK "Developer Command Prompt") is acceptable too.
  const probe = spawnSync("signtool", ["/?"], { stdio: "ignore" });
  return probe.error ? null : "signtool";
}

function signOne(file, { signtool, pfxPath, password }) {
  const args = ["sign", "/fd", "SHA256", "/td", "SHA256", "/tr", TIMESTAMP_URL];
  if (pfxPath) {
    args.push("/f", pfxPath, "/p", password);
  } else {
    args.push("/sha1", thumbprint());
  }
  args.push(file);
  const result = spawnSync(signtool, args, { encoding: "utf8", windowsHide: true });
  if (result.status !== 0) {
    const detail = `${result.stdout || ""}${result.stderr || ""}`.trim();
    throw new Error(`signtool failed for ${path.basename(file)}: ${detail || `exit ${result.status}`}`);
  }
}

/**
 * Sign the given files if certificate material is present. Never throws when
 * signing is not configured; throws when it IS configured and fails, because a
 * silently unsigned release is exactly the outcome we are avoiding.
 *
 * @param {string[]} files
 * @param {{ log?: (line: string) => void }} [options]
 * @returns {{ status: "signed" | "skipped" | "failed", reason?: string }}
 */
function signFiles(files, { log = console.log } = {}) {
  const list = files.filter(Boolean);
  if (list.length === 0) return { status: "skipped", reason: "no files" };
  if (!isConfigured()) {
    log(`  signing: ${describe()}`);
    return { status: "skipped", reason: "not configured" };
  }
  if (process.platform !== "win32") {
    log("  signing: not Windows — skipped");
    return { status: "skipped", reason: "not Windows" };
  }
  const signtool = findSigntool();
  if (!signtool) {
    const reason = "signtool.exe was not found — install the Windows SDK or set SIGNTOOL_PATH";
    log(`  signing: FAILED — ${reason}`);
    throw new Error(reason);
  }

  let tempDir = null;
  let pfxPath = null;
  try {
    if (pfxBase64()) {
      tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-sign-"));
      pfxPath = path.join(tempDir, "certificate.pfx");
      fs.writeFileSync(pfxPath, Buffer.from(pfxBase64(), "base64"), { mode: 0o600 });
    }
    for (const file of list) {
      if (!fs.existsSync(file)) throw new Error(`cannot sign a missing file: ${file}`);
      signOne(file, { signtool, pfxPath, password: process.env.WINDOWS_CERT_PASSWORD || "" });
      log(`  signed: ${path.basename(file)}`);
    }
    return { status: "signed" };
  } catch (err) {
    log(`  signing: FAILED — ${err.message}`);
    return { status: "failed", reason: err.message };
  } finally {
    if (tempDir) {
      try {
        fs.rmSync(tempDir, { recursive: true, force: true });
      } catch {}
    }
  }
}

module.exports = { signFiles, isConfigured, describe, findSigntool };

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args[0] === "--check") {
    console.log(`signing: ${describe()}`);
    if (isConfigured() && process.platform === "win32") {
      const signtool = findSigntool();
      console.log(`signtool: ${signtool || "NOT FOUND"}`);
      process.exit(signtool ? 0 : 1);
    }
    process.exit(0);
  }
  if (args.length === 0) {
    console.error("usage: node scripts/sign-windows.js --check | <file> [<file>...]");
    process.exit(2);
  }
  const result = signFiles(args, { log: (line) => console.log(line.trim()) });
  process.exit(result.status === "failed" ? 1 : 0);
}
