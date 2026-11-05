#!/usr/bin/env node
/*
 * Committed-secret scanner — the gate that keeps credentials out of git.
 *
 * WHY THIS EXISTS: `.gitignore` only stops a file that is *not* already tracked
 * and that nobody force-adds. One `git add -f .env` or one key pasted into a
 * source file permanently leaks the credential to every clone and to the public
 * internet once the repository is open source. This scanner is the second line
 * of defence, run by the pre-commit hook and by CI.
 *
 * It checks two things:
 *   1. PATHS — no tracked/staged file is a secret-bearing artifact (.env, a
 *      SQLite database, a private key, mcp-servers.json, the connector key).
 *   2. CONTENT — no file contains a recognisable provider credential or a
 *      private-key block.
 *
 * Modes:
 *   node scripts/scan-secrets.js            scan every tracked file (CI)
 *   node scripts/scan-secrets.js --staged   scan only the staged blobs (hook)
 *
 * Exit codes: 0 clean, 1 findings, 2 cannot run.
 *
 * Never prints a full secret: output is redacted to a short prefix + length so a
 * leak in the log cannot become a second leak.
 */
"use strict";

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const MAX_BYTES = 2 * 1024 * 1024; // skip anything bigger: no source file is this large
const STAGED = process.argv.includes("--staged");

function git(args, opts = {}) {
  return execFileSync("git", args, { encoding: "utf8", ...opts });
}

let ROOT;
try {
  ROOT = git(["rev-parse", "--show-toplevel"]).trim();
} catch {
  console.error("[scan-secrets] not inside a git work tree.");
  process.exit(2);
}

const toPosix = (p) => p.replace(/\\/g, "/");

// ── 1. Paths that must never be tracked ─────────────────────────────────────
// Matched against the repo-relative POSIX path. `.env.example` and friends are
// templates and are allowed on purpose.
const ALLOWED_ENV_TEMPLATES = new Set([".env.example", ".env.sample", ".env.template"]);

const FORBIDDEN_PATH = [
  { name: "environment file", re: /(^|\/)\.env$|(^|\/)\.env\.[^/]+$/ },
  { name: "SQLite database", re: /\.db(-wal|-shm|-journal)?$/ },
  { name: "connector encryption key", re: /(^|\/)\.connector-key$/ },
  { name: "channel gateway key", re: /(^|\/)channels\/secret\.key$/ },
  { name: "MCP config with possible secrets", re: /(^|\/)mcp-servers\.json$/ },
  // `.pem` is intentionally NOT a path rule: a public CA bundle is legitimately
  // committed. The content rule below still catches a private-key block in any
  // file. `.key`/`.p12`/`.pfx` are almost always secret material.
  { name: "private key material", re: /\.(p12|pfx|key)$/ },
  { name: "SSH private key", re: /(^|\/)id_(rsa|dsa|ecdsa|ed25519)$/ },
  { name: "runtime state", re: /(^|\/)\.black-eclipse\// },
];

function forbiddenPath(file) {
  const base = file.split("/").pop();
  if (ALLOWED_ENV_TEMPLATES.has(base)) return null;
  for (const rule of FORBIDDEN_PATH) {
    if (rule.re.test(file)) return rule.name;
  }
  return null;
}

// ── 2. Content patterns ─────────────────────────────────────────────────────
// Deliberately conservative: only shapes that are overwhelmingly a real
// credential. Example values are filtered by isPlaceholder() below.
const PATTERNS = [
  { name: "private key block", re: /-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----/g },
  { name: "OpenAI API key", re: /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/g },
  { name: "Anthropic API key", re: /\bsk-ant-[A-Za-z0-9_-]{20,}\b/g },
  { name: "GitHub token", re: /\bgh[pousr]_[A-Za-z0-9]{36,}\b/g },
  { name: "GitHub fine-grained token", re: /\bgithub_pat_[A-Za-z0-9_]{60,}\b/g },
  { name: "AWS access key id", re: /\bAKIA[0-9A-Z]{16}\b/g },
  { name: "Slack token", re: /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g },
  { name: "Google API key", re: /\bAIza[0-9A-Za-z_-]{35}\b/g },
  { name: "Stripe live key", re: /\bsk_live_[0-9A-Za-z]{20,}\b/g },
  { name: "npm token", re: /\bnpm_[A-Za-z0-9]{36}\b/g },
  { name: "GitLab token", re: /\bglpat-[A-Za-z0-9_-]{20,}\b/g },
  { name: "HuggingFace token", re: /\bhf_[A-Za-z0-9]{30,}\b/g },
  { name: "Telegram bot token", re: /\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b/g },
];

// Values a human or a test wrote on purpose. Kept as substrings so both
// `sk-abcdefghijklmnop` fixtures and `<your-key-here>` docs are ignored.
const PLACEHOLDER_MARKERS = [
  "abcdefghij",
  "1234567890",
  "123456789",
  "example",
  "placeholder",
  "change-me",
  "changeme",
  "xxxx",
  "your-",
  "your_",
  "redacted",
  "dummy",
  "sample",
  "fake",
  "<",
];

function isPlaceholder(value) {
  const v = value.toLowerCase();
  if (PLACEHOLDER_MARKERS.some((m) => v.includes(m))) return true;
  // One repeated character ("aaaaaaaa…") is a fixture, not a key.
  return new Set(v).size <= 2;
}

function redact(value) {
  return `${value.slice(0, 4)}…(${value.length} chars)`;
}

// Generated/vendored trees, fixtures and documentation are noise: they hold
// example tokens by design. Real secrets in these places are still caught by
// the PATH check where it matters.
const SKIP_CONTENT = [
  /(^|\/)(tests?|__tests__|fixtures)\//,
  /\.(test|spec)\.[cm]?[jt]sx?$/,
  /^Black-Eclipse-site\/docs\//,
  /^\.githooks\//,
  /^Black-Eclipse-site\/scripts\/scan-secrets\.js$/,
  /^Black-Eclipse-site\/\.env\.example$/,
  /\.lock$/,
  /\.map$/,
  /\.(png|jpe?g|gif|webp|ico|woff2?|ttf|eot|pdf|zip|gz|mp4|mov|wasm)$/i,
];

function skipContent(file) {
  return SKIP_CONTENT.some((re) => re.test(file));
}

// ── Input gathering ─────────────────────────────────────────────────────────
function listFiles() {
  if (STAGED) {
    const out = git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]);
    return out.split("\0").filter(Boolean).map(toPosix);
  }
  const out = git(["ls-files", "-z"]);
  return out.split("\0").filter(Boolean).map(toPosix);
}

function readContent(file) {
  try {
    if (STAGED) {
      const buf = execFileSync("git", ["show", `:${file}`], { maxBuffer: MAX_BYTES * 2 });
      if (buf.length > MAX_BYTES || buf.includes(0)) return null;
      return buf.toString("utf8");
    }
    const abs = path.join(ROOT, file);
    const stat = fs.statSync(abs);
    if (!stat.isFile() || stat.size > MAX_BYTES) return null;
    const buf = fs.readFileSync(abs);
    if (buf.includes(0)) return null;
    return buf.toString("utf8");
  } catch {
    return null; // deleted between listing and reading, or unreadable
  }
}

// ── Scan ────────────────────────────────────────────────────────────────────
const findings = [];
const files = listFiles();

for (const file of files) {
  const badPath = forbiddenPath(file);
  if (badPath) {
    findings.push({ file, line: 0, name: `tracked ${badPath}`, preview: "" });
    continue;
  }
  if (skipContent(file)) continue;

  const text = readContent(file);
  if (text === null) continue;
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    for (const { name, re } of PATTERNS) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(line)) !== null) {
        if (isPlaceholder(match[0])) continue;
        findings.push({ file, line: i + 1, name, preview: redact(match[0]) });
        if (findings.filter((f) => f.file === file && f.line === i + 1).length > 3) break;
      }
    }
  }
}

if (findings.length === 0) {
  if (!STAGED) console.log(`[scan-secrets] clean — ${files.length} tracked files scanned.`);
  process.exit(0);
}

const label = STAGED ? "staged" : "tracked";
console.error(`[scan-secrets] ${findings.length} potential secret(s) in ${label} files:\n`);
for (const f of findings) {
  const where = f.line ? `${f.file}:${f.line}` : f.file;
  console.error(`  • ${where}  →  ${f.name}${f.preview ? `  (${f.preview})` : ""}`);
}
console.error(
  "\nRemove the file from git (`git rm --cached <path>`), delete the credential," +
    "\nrotate it, and add an ignore rule. If this is a known false positive, add a" +
    "\nnarrow rule to scripts/scan-secrets.js rather than skipping the whole scan.",
);
process.exit(1);
