#!/usr/bin/env node
// ── Update signing keys ──────────────────────────────────────────────────────
// Generates the Ed25519 keypair behind update manifests.
//
//   node scripts/update-keys.js generate [--force]
//   node scripts/update-keys.js fingerprint
//
// The PRIVATE key is written to `.black-eclipse/update-keys/` (gitignored) and
// must then be moved OFF this machine — a hardware token / encrypted USB /
// offline machine. It must never be committed, pasted into CI, or left beside a
// publicly reachable install. The PUBLIC key is committed at
// `config/update-signing-key.pub`; shipping it is what lets every install
// verify that an update really came from you.
//
// Losing the private key: users simply stop getting updates until you publish a
// release that ships a new public key (rotate by committing the new .pub in a
// normal, reviewed release).
// Leaking the private key: an attacker can sign a malicious update, so rotate
// immediately — publish a release with a new public key, then revoke the old
// key in the release notes and docs/UPDATES.md.

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { keyFingerprint, PUBLIC_KEY_PATH } = require("./lib/update-verify");

const ROOT = path.join(__dirname, "..");
const KEY_DIR = path.join(ROOT, ".black-eclipse", "update-keys");
const PRIVATE_KEY_PATH = path.join(KEY_DIR, "update-signing-key.pem");

function generate({ force }) {
  if (fs.existsSync(PRIVATE_KEY_PATH) && !force) {
    console.error(`Refusing to overwrite an existing private key: ${PRIVATE_KEY_PATH}`);
    console.error("Pass --force only if you intend to rotate (all future manifests must be re-signed).");
    process.exit(1);
  }

  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  const privatePem = privateKey.export({ type: "pkcs8", format: "pem" });
  const publicPem = publicKey.export({ type: "spki", format: "pem" });

  fs.mkdirSync(KEY_DIR, { recursive: true, mode: 0o700 });
  fs.writeFileSync(PRIVATE_KEY_PATH, privatePem, { mode: 0o600 });
  fs.mkdirSync(path.dirname(PUBLIC_KEY_PATH), { recursive: true });
  fs.writeFileSync(PUBLIC_KEY_PATH, publicPem, "utf8");

  const fingerprint = keyFingerprint(publicPem);
  console.log("");
  console.log("  Update signing keypair created.");
  console.log(`  private key : ${PRIVATE_KEY_PATH}`);
  console.log(`  public key  : ${PUBLIC_KEY_PATH}  (commit this)`);
  console.log(`  key id      : ${fingerprint.slice(0, 16)}`);
  console.log("");
  console.log("  NEXT STEPS");
  console.log("  1. Move the private key to an offline location now.");
  console.log("     Do not commit it. Do not put it in GitHub Actions secrets.");
  console.log("  2. Commit config/update-signing-key.pub in a normal reviewed release.");
  console.log("  3. Publish that release to users, then sign future manifests with it.");
  console.log("");
}

function printFingerprint() {
  try {
    const pem = fs.readFileSync(PUBLIC_KEY_PATH, "utf8");
    console.log(keyFingerprint(pem));
  } catch {
    console.error(`No public key at ${PUBLIC_KEY_PATH}. Run "node scripts/update-keys.js generate" first.`);
    process.exit(1);
  }
}

const command = process.argv[2] || "generate";
if (command === "generate") {
  generate({ force: process.argv.includes("--force") });
} else if (command === "fingerprint") {
  printFingerprint();
} else {
  console.error(`Unknown command "${command}". Use: generate | fingerprint`);
  process.exit(1);
}
