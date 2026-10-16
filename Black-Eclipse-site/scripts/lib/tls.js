// Shared helper for the local HTTPS (TLS) setup — used by the reverse proxy
// (`scripts/local-proxy.js`) and the launcher (`scripts/local-host.js`).
//
// Why this exists: the browser's Web Notification API (and service workers,
// clipboard, and other powerful features) require a SECURE CONTEXT. A plain
// `http://blackeclipse` hosts-file alias is NOT one — only `https://…` or the
// loopback names `localhost`/`127.0.0.1`/`[::1]` are. Terminating TLS at the
// local proxy with a locally-trusted certificate restores `https://blackeclipse`
// as a secure origin, so desktop notifications work there.
//
// The certificate + passphrase live under `.black-eclipse/certs/` (gitignored):
//   blackeclipse.pfx   PKCS#12 bundle (cert + private key) read by Node's TLS
//   blackeclipse.pass  the PFX passphrase, stored next to it
// They are produced by `scripts/setup-tls.ps1` (`npm run setup:tls`).

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const CERT_DIR = path.join(root, ".black-eclipse", "certs");

/** Resolve the certificate file paths for a local hostname. */
function certPaths(name = process.env.BE_LOCAL_HOSTNAME || "blackeclipse") {
  return {
    dir: CERT_DIR,
    pfx: path.join(CERT_DIR, `${name}.pfx`),
    crt: path.join(CERT_DIR, `${name}.crt`),
    passphrase: path.join(CERT_DIR, `${name}.pass`),
  };
}

/** True when a usable PFX + passphrase pair is present on disk. */
function tlsAvailable(name) {
  const p = certPaths(name);
  return fs.existsSync(p.pfx) && fs.existsSync(p.passphrase);
}

/**
 * The options for `https.createServer`, or `null` when no certificate is
 * provisioned. Returns `{ pfx, passphrase }` (Node reads both natively).
 */
function tlsConfig(name) {
  if (!tlsAvailable(name)) return null;
  const p = certPaths(name);
  try {
    return {
      pfx: fs.readFileSync(p.pfx),
      passphrase: fs.readFileSync(p.passphrase, "utf8").trim(),
    };
  } catch {
    return null;
  }
}

module.exports = { CERT_DIR, certPaths, tlsAvailable, tlsConfig };
