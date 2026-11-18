#!/usr/bin/env node
// Build the Windows installer, its checksum, and the winget manifests.
//
// Requires NSIS (`winget install NSIS.NSIS`) and a prior
// `npm run desktop:build && npm run desktop:payload && npm run desktop:package`.
//
// Outputs, all under dist/:
//   BlackEclipse-Setup-<version>.exe
//   SHA256SUMS.txt
//   winget/<Publisher>.<Package>/<version>/*.yaml

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const DIST = path.join(ROOT, "dist");
const APP_DIR = path.join(DIST, "BlackEclipse");
const NSI = path.join(ROOT, "desktop", "installer", "BlackEclipse.nsi");

const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
const VERSION = pkg.version;
const FULL = process.argv.includes("--full");

// MUI2 reads these at compile time; a missing bitmap otherwise fails with a
// generic makensis error that points at the include file, not the asset.
const ASSETS = ["icon.ico", "welcome.bmp", "header.bmp"].map((name) => ({
  name,
  file: path.join(ROOT, "desktop", "installer", "assets", name),
}));
for (const asset of ASSETS) {
  if (!fs.existsSync(asset.file)) {
    console.error(
      `Missing installer asset: desktop/installer/assets/${asset.name}\n` +
        "Regenerate the committed bitmaps with: node scripts/make-installer-assets.js"
    );
    process.exit(6);
  }
}

const OUT_EXE = path.join(
  DIST,
  `BlackEclipse-Setup-${VERSION}${FULL ? "-full" : ""}.exe`
);

const MAKENSIS_CANDIDATES = [  "makensis",
  path.join(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)", "NSIS", "makensis.exe"),
  path.join(process.env.ProgramFiles || "C:\\Program Files", "NSIS", "makensis.exe"),
];

function findMakensis() {
  for (const candidate of MAKENSIS_CANDIDATES) {
    if (candidate === "makensis") {
      const probe = spawnSync("makensis", ["/VERSION"], { encoding: "utf8" });
      if (probe.status === 0) return "makensis";
      continue;
    }
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function sha256(file) {  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(file));
  return hash.digest("hex");
}

if (!fs.existsSync(path.join(APP_DIR, "Black Eclipse.exe"))) {
  console.error("No assembled app. Run `npm run desktop:package` first.");
  process.exit(1);
}

const makensis = findMakensis();
if (!makensis) {
  console.error(
    "NSIS not found. Install it once with:\n  winget install --id NSIS.NSIS -e\n" +
      "The release workflow installs it automatically in CI."
  );
  process.exit(2);
}

const appMB = (() => {
  let total = 0;
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.isFile()) total += fs.statSync(p).size;
    }
  };
  walk(APP_DIR);
  return total / (1024 * 1024);
})();

console.log(`Building Black Eclipse ${VERSION} installer`);
console.log(`  payload: ${appMB.toFixed(0)} MB (LZMA solid — this takes several minutes)\n`);

const started = Date.now();

// The payload is a build tree, but running the app from it writes runtime state
// (logs, lock files). A lock file can even fail to open during compression, so
// strip that state before packaging. It is recreated on the user's machine.
try {
  fs.rmSync(path.join(APP_DIR, ".black-eclipse"), { recursive: true, force: true });
} catch {}

const APP_DIR_FOR_BUILD = APP_DIR;

// NSIS resolves paths with the classic 260-character limit, and this repository
// lives under a long path. Build through a short junction so makensis never sees
// the deep path; the installed layout is short enough on its own.
const SHORT_LINK = path.join(process.env.LOCALAPPDATA || os.tmpdir(), "bepl");
const PACKS_LINK = path.join(process.env.LOCALAPPDATA || os.tmpdir(), "beplp");
try {
  fs.rmSync(SHORT_LINK, { recursive: false, force: true });
} catch {}
fs.mkdirSync(path.dirname(SHORT_LINK), { recursive: true });
try {
  fs.symlinkSync(APP_DIR, SHORT_LINK, "junction");
} catch (err) {
  console.error(`Could not create the short build path ${SHORT_LINK}: ${err.message}`);
}

if (FULL) {
  const packsDir = path.join(DIST, "packs");
  const required = ["browser", "ml", "documents", "computer", "charts"];
  const present = required.filter((p) => fs.existsSync(path.join(packsDir, p, "site-packages")));
  const missing = required.filter((p) => !present.includes(p));

  // A platform may legitimately lack a pack (winsdk has no Linux wheel), so the
  // offline edition includes whatever exists instead of failing the whole build.
  if (present.length === 0) {
    console.error("Full installer needs at least one pack; none were built.");
    process.exit(4);
  }
  if (missing.length) {
    console.log(`  offline edition includes ${present.join(", ")}; skipping ${missing.join(", ")}`);
  }

  try {
    fs.rmSync(PACKS_LINK, { recursive: false, force: true });
  } catch {}
  try {
    fs.symlinkSync(packsDir, PACKS_LINK, "junction");
  } catch (err) {
    console.error(`Could not create the short packs path ${PACKS_LINK}: ${err.message}`);
  }

  // NSIS cannot loop over a list at compile time, so generate the File lines.
  const includePath = path.join(DIST, "packs-include.nsi");
  fs.writeFileSync(
    includePath,
    present
      .map((p) => `  File /r "${PACKS_LINK}\\${p}\\site-packages\\*"`)
      .join("\n") + "\n"
  );
}

const defines = [
  "/V2",
  `/DAPP_VERSION=${VERSION}`,
  `/DSRCDIR=${SHORT_LINK}`,
  `/DOUTFILE=${OUT_EXE}`,
];
if (FULL) {
  defines.push(
    "/DFULL",
    `/DPACKSDIR=${PACKS_LINK}`,
    `/DPACKSINCLUDE=${path.join(DIST, "packs-include.nsi")}`
  );
}

// WebView2 Evergreen bootstrapper (~2 MB) bundled into the installer so a
// Windows 10 machine without the runtime can be fixed during setup instead of
// opening an app that immediately exits. Build-time only; never shipped as a
// separate download.
const WV2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";
function webView2Bootstrapper() {
  const dest = path.join(ROOT, ".black-eclipse", "webview2", "MicrosoftEdgeWebview2Setup.exe");
  try {
    if (fs.existsSync(dest) && fs.statSync(dest).size > 1_000_000) return dest;
  } catch {}
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  console.log("  webview2: downloading the Evergreen bootstrapper");
  const r = spawnSync("curl", ["-fsSL", "--retry", "3", "-o", dest, WV2_URL], { stdio: "ignore" });
  if (r.status === 0 && fs.existsSync(dest) && fs.statSync(dest).size > 1_000_000) {
    return dest;
  }
  console.log("  webview2: bootstrapper unavailable — the installer will explain instead");
  return null;
}

const wv2 = webView2Bootstrapper();
if (wv2) {
  defines.push(`/DWEBVIEW2_BOOTSTRAPPER=${wv2}`);
}

const result = spawnSync(makensis, [...defines, NSI], { stdio: "inherit", cwd: ROOT });

try {
  fs.rmSync(SHORT_LINK, { force: true });
  fs.rmSync(PACKS_LINK, { force: true });
} catch {}

if (result.status !== 0 || !fs.existsSync(OUT_EXE)) {
  console.error(`\nmakensis failed (exit ${result.status}).`);
  process.exit(result.status || 3);
}

const installerMB = fs.statSync(OUT_EXE).size / (1024 * 1024);
const digest = sha256(OUT_EXE);
console.log(
  `\nInstaller: ${path.relative(ROOT, OUT_EXE)} (${installerMB.toFixed(0)} MB) in ${Math.round(
    (Date.now() - started) / 1000
  )}s`
);
console.log(`SHA-256:   ${digest}`);

// Stable download alias. The README's Download button links to
// `releases/latest/download/BlackEclipse-Setup.exe`, so a version-independent
// name must exist on every release; otherwise the button breaks each version.
// The alias always mirrors the SLIM installer — never the offline (-full)
// edition, and never a stale file from a previous run.
const SLIM_EXE = path.join(DIST, `BlackEclipse-Setup-${VERSION}.exe`);
const ALIAS_EXE = path.join(DIST, "BlackEclipse-Setup.exe");
if (fs.existsSync(SLIM_EXE)) {
  fs.copyFileSync(SLIM_EXE, ALIAS_EXE);
  console.log(`Alias:     dist/BlackEclipse-Setup.exe (stable download URL)`);
} else if (FULL) {
  // An offline-only build must never ship a slim alias from an older version —
  // the release would then serve a stale installer to the Download button.
  if (fs.existsSync(ALIAS_EXE)) {
    fs.rmSync(ALIAS_EXE, { force: true });
    console.log(`Alias:     removed stale dist/BlackEclipse-Setup.exe (no slim build this run)`);
  }
} else {
  console.error(`Could not create the stable download alias: ${path.basename(SLIM_EXE)} missing.`);
  process.exit(5);
}

// Checksum file for GitHub Releases — expected practice for an unsigned binary.
// Includes every installer currently present (slim, offline, and the alias).
const sums = fs
  .readdirSync(DIST)
  .filter((f) => /^BlackEclipse-Setup(-.*)?\.exe$/.test(f))
  .sort()
  .map((f) => `${sha256(path.join(DIST, f))}  ${f}`)
  .join("\n");
fs.writeFileSync(path.join(DIST, "SHA256SUMS.txt"), `${sums}\n`);
console.log(`Wrote     dist/SHA256SUMS.txt (${sums.split("\n").length} installer(s))`);

/* ------------------------------------------------------------------ winget */

// winget needs a manifest trio. The hash is what makes `winget install` verify
// the download, and winget strips the Mark-of-the-Web, so the SmartScreen wall
// is usually skipped entirely.
const WINGET_DIR = path.join(DIST, "winget", "BlackEclipse.BlackEclipse", VERSION);
fs.mkdirSync(WINGET_DIR, { recursive: true });

const installerUrl = `https://github.com/black-eclipse/black-eclipse/releases/download/v${VERSION}/BlackEclipse-Setup-${VERSION}.exe`;

fs.writeFileSync(
  path.join(WINGET_DIR, "BlackEclipse.BlackEclipse.yaml"),
  `# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.1.6.0.schema.json
PackageIdentifier: BlackEclipse.BlackEclipse
PackageVersion: ${VERSION}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.6.0
`
);

fs.writeFileSync(
  path.join(WINGET_DIR, "BlackEclipse.BlackEclipse.locale.en-US.yaml"),
  `# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.1.6.0.schema.json
PackageIdentifier: BlackEclipse.BlackEclipse
PackageVersion: ${VERSION}
PackageLocale: en-US
Publisher: BlackEclipse
PublisherUrl: https://github.com/black-eclipse/black-eclipse
PackageName: Black Eclipse
PackageUrl: https://github.com/black-eclipse/black-eclipse
License: MIT
LicenseUrl: https://github.com/black-eclipse/black-eclipse/blob/main/LICENSE
ShortDescription: Local-first market research and trading workspace with an agent harness.
Description: Black Eclipse runs entirely on your machine. No account, no sign-in, no telemetry. Your data stays in %LOCALAPPDATA%\\BlackEclipse\\data.
Moniker: blackeclipse
Tags: [finance, trading, market-data, ai, agent]
ManifestType: defaultLocale
ManifestVersion: 1.6.0
`
);

fs.writeFileSync(
  path.join(WINGET_DIR, "BlackEclipse.BlackEclipse.installer.yaml"),
  `# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.1.6.0.schema.json
PackageIdentifier: BlackEclipse.BlackEclipse
PackageVersion: ${VERSION}
Platform:
  - Windows.Desktop
MinimumOSVersion: 10.0.0.0
InstallerType: nullsoft
Scope: user
InstallModes:
  - interactive
  - silent
UpgradeBehavior: install
ReleaseDate: ${new Date().toISOString().slice(0, 10)}
Installers:
  - Architecture: x64
    InstallerUrl: ${installerUrl}
    InstallerSha256: ${digest.toUpperCase()}
    ProductCode: BlackEclipse
ManifestType: installer
ManifestVersion: 1.6.0
`
);

console.log(`Wrote     dist/winget/BlackEclipse.BlackEclipse/${VERSION}/ (3 manifests)`);
console.log(`\nUnsigned installer — publish SHA256SUMS.txt next to it so users can verify.`);
