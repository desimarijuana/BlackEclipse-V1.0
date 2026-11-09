#!/usr/bin/env node
// ── Sign a release manifest ──────────────────────────────────────────────────
// Run this locally, on the machine that holds the OFFLINE private key, after the
// release tag exists:
//
//   node scripts/update-sign.js --version 0.4.0 --channel stable --commit <sha>
//
// It writes `release/stable.json` (gitignored). Upload that file as an asset on
// the GitHub Release. The app reads it from
// `.../releases/latest/download/stable.json`.
//
// Optional flags:
//   --notes-url <url>       "What's new" link (defaults to the release page)
//   --download-url <url>    archive / source zip link
//   --min-supported <ver>   oldest version you will keep supporting
//   --key <path>            private key (default .black-eclipse/update-keys/...)
//   --out <path>            output file (default release/<channel>.json)
//   --force                 allow re-signing an existing output file

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const {
  ENVELOPE_SCHEMA,
  ROOT,
  readConfig,
  loadPublicKey,
  verifyEnvelope,
} = require("./lib/update-verify");

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  if (i !== -1 && process.argv[i + 1]) return process.argv[i + 1];
  return fallback;
}

function fail(message) {
  console.error(`[update-sign] ${message}`);
  process.exit(1);
}

const channel = arg("channel", "stable");
if (!["stable", "beta"].includes(channel)) fail(`unknown channel "${channel}"`);

const cfg = readConfig();
const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
const version = arg("version", pkg.version);
if (!/^v?\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$/.test(version)) {
  fail(`invalid version "${version}"`);
}
const normalizedVersion = version.replace(/^v/, "");

const commit = arg("commit", "");
if (!/^[0-9a-f]{40}$/.test(commit)) {
  fail("--commit must be the full 40-character git commit SHA of the release tag");
}

const notesUrl =
  arg("notes-url", "") || `https://github.com/${cfg.repository}/releases/tag/v${normalizedVersion}`;
const downloadUrl =
  arg("download-url", "") ||
  `https://github.com/${cfg.repository}/archive/refs/tags/v${normalizedVersion}.zip`;

const payload = {
  schema: 1,
  channel,
  version: normalizedVersion,
  publishedAt: new Date().toISOString(),
  commit,
  notesUrl,
  downloadUrl,
};
const minSupported = arg("min-supported", "");
if (minSupported) payload.minSupported = minSupported.replace(/^v/, "");

const keyPath = arg("key", path.join(ROOT, ".black-eclipse", "update-keys", "update-signing-key.pem"));
if (!fs.existsSync(keyPath)) fail(`private key not found: ${keyPath}`);

const privateKey = crypto.createPrivateKey(fs.readFileSync(keyPath, "utf8"));
if (privateKey.asymmetricKeyType !== "ed25519") fail("signing key must be Ed25519");

const payloadBytes = Buffer.from(JSON.stringify(payload), "utf8");
const envelope = {
  schema: ENVELOPE_SCHEMA,
  payload: payloadBytes.toString("base64url"),
  signature: crypto.sign(null, payloadBytes, privateKey).toString("base64url"),
};
const envelopeJson = JSON.stringify(envelope, null, 2) + "\n";

// Self-check with the committed public key BEFORE writing anything: a manifest
// the releases page cannot verify is worse than no manifest at all.
try {
  verifyEnvelope(envelopeJson, loadPublicKey(), channel);
} catch (err) {
  fail(`self-verification failed (public key does not match this private key?): ${err.message}`);
}

const outPath = arg("out", path.join(ROOT, "release", `${channel}.json`));
if (fs.existsSync(outPath) && !process.argv.includes("--force")) {
  fail(`${outPath} already exists; pass --force to overwrite`);
}
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, envelopeJson, "utf8");

console.log(`[update-sign] signed ${channel} v${normalizedVersion} -> ${outPath}`);
console.log(`[update-sign] commit ${commit}`);
console.log("[update-sign] next: upload this file as a GitHub Release asset");
