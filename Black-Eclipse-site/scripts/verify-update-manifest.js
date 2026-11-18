#!/usr/bin/env node
// Release gate for the signed update manifest.
//
// The app trusts a public manifest only after its Ed25519 signature verifies, so
// a stale or unsigned `stable.json` is worse than none: every installed client
// checks it. This script answers "does the manifest we are about to attach
// describe THIS release?" before the asset is published.
//
//   node scripts/verify-update-manifest.js                 stable + beta (if present)
//   node scripts/verify-update-manifest.js --channel beta
//   node scripts/verify-update-manifest.js --allow-missing  don't fail on absence
//   node scripts/verify-update-manifest.js --json
//
// Fails when: updates are published and the manifest is missing (a 404 breaks
// every update check), the signature does not verify with the committed public
// key, or the signed version differs from package.json.
// Warns (does not fail) when the signed commit differs from GITHUB_SHA: the tag
// may legitimately be cut from another commit, but then clients are not offered
// this release until the manifest is re-signed.

const fs = require("fs");
const path = require("path");
const { verifyEnvelope, loadPublicKey } = require("./lib/update-verify");

const ROOT = path.join(__dirname, "..");
const CONFIG_PATH = path.join(ROOT, "config", "updates.json");
const PUBLIC_KEY_PATH = path.join(ROOT, "config", "update-signing-key.pub");
const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));

const argv = process.argv.slice(2);
const flag = (name) => argv.includes(`--${name}`);
const arg = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i !== -1 && argv[i + 1] ? argv[i + 1] : fallback;
};

const onlyChannel = arg("channel", null);
const allowMissing = flag("allow-missing");
const asJson = flag("json");

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
  } catch {
    return {};
  }
}

const config = readConfig();
const published = config.published !== false;
const gitSha = (process.env.GITHUB_SHA || "").trim();
const channels = onlyChannel ? [onlyChannel] : ["stable", "beta"];

const report = { version: pkg.version, published, channels: [], ok: true };

for (const channel of channels) {
  const file = path.join(ROOT, "release", `${channel}.json`);
  const entry = { channel, file: path.relative(ROOT, file), exists: fs.existsSync(file) };

  if (!entry.exists) {
    entry.status = published ? "missing" : "missing-ok";
    if (published && !allowMissing && channel === "stable") {
      entry.error =
        `Updates are published (config/updates.json) but release/${channel}.json is missing. ` +
        `A 404 here breaks every client's update check. Sign one with ` +
        `\`npm run update:sign -- --channel ${channel}\`.`;
      report.ok = false;
    }
    report.channels.push(entry);
    continue;
  }

  try {
    const envelope = fs.readFileSync(file, "utf8");
    const payload = verifyEnvelope(envelope, loadPublicKey(fs.readFileSync(PUBLIC_KEY_PATH, "utf8")), channel);
    entry.version = payload.version;
    entry.commit = payload.commit;

    if (payload.version !== pkg.version) {
      entry.status = "version-mismatch";
      entry.error =
        `release/${channel}.json describes v${payload.version}, but package.json is ${pkg.version}. ` +
        `Re-sign after bumping the version.`;
      report.ok = false;
    } else {
      entry.status = "verified";
    }

    if (gitSha && payload.commit && payload.commit !== gitSha) {
      entry.warning =
        `Manifest commit ${payload.commit.slice(0, 7)} ≠ release commit ${gitSha.slice(0, 7)}; ` +
        `clients will keep reporting "up to date" until it is re-signed from this commit.`;
    }
  } catch (err) {
    entry.status = "invalid";
    entry.error = err && err.message ? err.message : String(err);
    report.ok = false;
  }

  report.channels.push(entry);
}

if (asJson) {
  console.log(JSON.stringify(report, null, 2));
} else {
  console.log(`Signed update manifest — package version ${pkg.version}`);
  console.log(`Updates published: ${published ? "yes" : "no"}`);
  for (const entry of report.channels) {
    console.log(`\n  ${entry.channel}: ${entry.file} (${entry.status})`);
    if (entry.version) console.log(`    version ${entry.version} · commit ${String(entry.commit).slice(0, 7)}`);
    if (entry.warning) console.log(`    WARNING ${entry.warning}`);
    if (entry.error) console.log(`    ERROR   ${entry.error}`);
  }
  console.log(report.ok ? "\nOK" : "\nFAILED");
}

process.exit(report.ok ? 0 : 1);
