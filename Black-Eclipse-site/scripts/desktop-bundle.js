#!/usr/bin/env node
// Build the OS-native artifact for the current platform.
//
//   Windows  -> delegate to `desktop-installer.js` (NSIS). Run `npm run desktop:installer`.
//   Linux    -> .deb via `dpkg-deb` (present on Debian/Ubuntu runners)
//   macOS    -> .app bundle + ad-hoc signature + .dmg via `hdiutil`
//
// Why not one tool for all three: NSIS, dpkg and hdiutil are the *native*
// packaging formats, they are preinstalled on the matching OS, and none of them
// needs a cross-toolchain. A cross-platform packager would add a large
// dependency to solve a problem the OS already solves.
//
// Layout is identical on every platform:
//   <root>/app        Next standalone payload + python + scripts
//   <root>/runtime    node[.exe]
//   <root>/Black Eclipse[.exe]   Tauri binary
//
// Inputs: run `desktop:package` for the current platform first.

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { betterSqliteDir, canLoadBetterSqlite } = require("./lib/native-modules");

const ROOT = path.join(__dirname, "..");
const DIST = path.join(ROOT, "dist");
const APP_ROOT = path.join(DIST, "BlackEclipse");
const VERSION = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8")).version;
const TARGET = `${process.platform}-${process.arch}`;
// `--dry-run` builds the staging tree but skips the OS packaging tool
// (`dpkg-deb`, `codesign`, `hdiutil`). It proves the layout code on a machine
// that cannot run the native tool â€” the only way to test this off-platform.
const DRY_RUN = process.argv.includes("--dry-run");

function sh(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: "inherit", ...opts });
  if (r.status !== 0) {
    console.error(`[bundle] ${cmd} ${args.join(" ")} failed (exit ${r.status})`);
    process.exit(r.status || 1);
  }
}

function copyTree(from, to) {
  fs.cpSync(from, to, { recursive: true });
}

// The payload's binary is named per platform. A dry run on Windows must find
// `Black Eclipse.exe` while a real Linux/macOS build finds `Black Eclipse`.
function shellBinaryName() {
  for (const name of ["Black Eclipse", "Black Eclipse.exe"]) {
    if (fs.existsSync(path.join(APP_ROOT, name))) return name;
  }
  console.error("[bundle] no shell binary in dist/BlackEclipse â€” run desktop:package first");
  process.exit(1);
}

/* ------------------------------------------------------------------- linux */

function buildDeb() {
  const stage = path.join(DIST, `deb-${TARGET}`);
  fs.rmSync(stage, { recursive: true, force: true });

  const lib = path.join(stage, "usr", "lib", "blackeclipse");
  fs.mkdirSync(lib, { recursive: true });
  copyTree(path.join(APP_ROOT, "app"), path.join(lib, "app"));
  copyTree(path.join(APP_ROOT, "runtime"), path.join(lib, "runtime"));
  const shellName = shellBinaryName(); fs.copyFileSync(path.join(APP_ROOT, shellName), path.join(lib, shellName));
  fs.chmodSync(path.join(lib, shellName), 0o755);

  fs.mkdirSync(path.join(stage, "usr", "bin"), { recursive: true });
  // A symlink is the correct Debian layout. Creating one needs privileges on
  // Windows (where this runs dry), so fall back to an equivalent sh wrapper.
  try {
    fs.symlinkSync("../lib/blackeclipse/Black Eclipse", path.join(stage, "usr", "bin", "blackeclipse"));
  } catch {
    const wrapper = path.join(stage, "usr", "bin", "blackeclipse");
    fs.writeFileSync(
      wrapper,
      '#!/bin/sh\nexec "/usr/lib/blackeclipse/Black Eclipse" "$@"\n'
    );
    fs.chmodSync(wrapper, 0o755);
  }

  const applications = path.join(stage, "usr", "share", "applications");
  fs.mkdirSync(applications, { recursive: true });
  fs.writeFileSync(
    path.join(applications, "blackeclipse.desktop"),
    [
      "[Desktop Entry]",
      "Type=Application",
      "Name=Black Eclipse",
      "Comment=Local-first market research and trading workspace",
      "Exec=/usr/lib/blackeclipse/Black Eclipse",
      "Terminal=false",
      "Categories=Office;Finance;",
      "StartupWMClass=black-eclipse-desktop",
      "",
    ].join("\n")
  );

  const control = path.join(stage, "DEBIAN");
  fs.mkdirSync(control, { recursive: true });
  const installedKb = Math.ceil(
    (() => {
      let total = 0;
      const walk = (d) => {
        for (const e of fs.readdirSync(d, { withFileTypes: true })) {
          const p = path.join(d, e.name);
          if (e.isSymbolicLink()) continue;
          if (e.isDirectory()) walk(p);
          else total += fs.statSync(p).size;
        }
      };
      walk(stage);
      return total / 1024;
    })()
  );
  fs.writeFileSync(
    path.join(control, "control"),
    [
      `Package: blackeclipse`,
      `Version: ${VERSION}`,
      `Section: misc`,
      `Priority: optional`,
      `Architecture: ${process.arch === "arm64" ? "arm64" : "amd64"}`,
      `Installed-Size: ${installedKb}`,
      `Maintainer: BlackEclipse <noreply@blackeclipse.dev>`,
      `Homepage: https://github.com/blackeclipse/black-eclipse`,
      `Description: Local-first market research and trading workspace`,
      ` Runs entirely on the local machine with a bundled Node and Python runtime.`,
      ` No account, no telemetry; data lives in ~/.local/share/BlackEclipse.`,
      "",
    ].join("\n")
  );

  const arch = process.arch === "arm64" ? "arm64" : "amd64";
  const out = path.join(DIST, `blackeclipse_${VERSION}_${arch}.deb`);
  if (DRY_RUN) {
    console.log(`[bundle] dry run: staged ${path.relative(ROOT, stage)} (dpkg-deb skipped)`);
    console.log(`[bundle] would write ${path.relative(ROOT, out)}`);
    return;
  }
  sh("dpkg-deb", ["--build", "--root-owner-group", stage, out]);
  console.log(`\n[bundle] ${path.relative(ROOT, out)}`);

  // Stable download alias — the README's Linux button links to
  // `releases/latest/download/BlackEclipse-linux-amd64.deb`, so the name must
  // survive a version bump. See docs/desktop-size-plan.md (download contract).
  const alias = path.join(DIST, `BlackEclipse-linux-${arch}.deb`);
  fs.copyFileSync(out, alias);
  console.log(`[bundle] alias ${path.relative(ROOT, alias)}`);
}

/* ------------------------------------------------------------------- macos */

function buildMac() {
  const appName = "Black Eclipse.app";
  const bundle = path.join(DIST, appName);
  fs.rmSync(bundle, { recursive: true, force: true });

  const contents = path.join(bundle, "Contents");
  const macos = path.join(contents, "MacOS");
  fs.mkdirSync(macos, { recursive: true });

  copyTree(path.join(APP_ROOT, "app"), path.join(macos, "app"));
  copyTree(path.join(APP_ROOT, "runtime"), path.join(macos, "runtime"));
  fs.copyFileSync(path.join(APP_ROOT, shellBinaryName()), path.join(macos, "black-eclipse-desktop"));
  fs.chmodSync(path.join(macos, "black-eclipse-desktop"), 0o755);

  fs.writeFileSync(
    path.join(contents, "Info.plist"),
    `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Black Eclipse</string>
  <key>CFBundleDisplayName</key><string>Black Eclipse</string>
  <key>CFBundleIdentifier</key><string>com.blackeclipse.desktop</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>black-eclipse-desktop</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
`
  );

  // Ad-hoc signature: enough to run locally and to test. It does NOT satisfy
  // Gatekeeper for downloads â€” that needs notarisation (plan phase C5).
  if (DRY_RUN) {
    console.log(`[bundle] dry run: staged ${path.relative(ROOT, bundle)} (codesign + hdiutil skipped)`);
    return;
  }
  // `--deep` must NOT be used: it descends into the payload
  // (`app/node_modules/...`) and fails with "bundle format unrecognized" on
  // files such as next's `lodash.curry`. Sign the executable, then the bundle.
  // Best effort: an unsigned .dmg is still produced, and Gatekeeper needs
  // notarisation (C5) regardless.
  const trySign = (args) => spawnSync("codesign", args, { stdio: "inherit" }).status === 0;
  const signedBinary = trySign(["--force", "--sign", "-", path.join(macos, "black-eclipse-desktop")]);
  const signedBundle = trySign(["--force", "--sign", "-", bundle]);
  if (!signedBinary || !signedBundle) {
    console.log("[bundle] ad-hoc signing failed; continuing with an unsigned bundle");
  }

  const dmg = path.join(DIST, `BlackEclipse-${VERSION}-${process.arch}.dmg`);
  fs.rmSync(dmg, { force: true });
  sh("hdiutil", [
    "create",
    "-volname",
    "Black Eclipse",
    "-srcfolder",
    bundle,
    "-ov",
    "-format",
    "UDZO",
    dmg,
  ]);
  console.log(`\n[bundle] ${path.relative(ROOT, dmg)}`);
  console.log("[bundle] ad-hoc signed. Gatekeeper will still block a download until notarised (C5).");

  // Stable download alias. The arch is IN the name because a Mac cannot run the
  // other arch's build, and only one arch is produced per runner: the README
  // links `BlackEclipse-mac-arm64.dmg` explicitly rather than silently handing
  // an Intel Mac a binary it can never launch.
  const alias = path.join(DIST, `BlackEclipse-mac-${process.arch}.dmg`);
  fs.copyFileSync(dmg, alias);
  console.log(`[bundle] alias ${path.relative(ROOT, alias)}`);
}

/* ------------------------------------------------------------------ main */

if (!fs.existsSync(APP_ROOT)) {
  console.error("[bundle] No packaged app. Run `npm run desktop:package` first.");
  process.exit(1);
}

// A payload without Prisma's nested better-sqlite3 binary still boots and serves
// HTTP; only this probe catches the broken onboarding database before a .dmg or
// .deb is produced.
if (!canLoadBetterSqlite(process.execPath, betterSqliteDir(path.join(APP_ROOT, "app")))) {
  console.error(
    "[bundle] The packaged app cannot open its SQLite database (better-sqlite3 binding missing).\n" +
      "Re-run `npm run desktop:package` before bundling."
  );
  process.exit(1);
}

// `--target deb|mac` lets a non-matching host exercise the layout code.
const forced = (arg) => process.argv.includes("--target") && process.argv[process.argv.indexOf("--target") + 1] === arg;
const mode = forced("deb") ? "deb" : forced("mac") ? "mac" : process.platform;

if (mode === "win32") {
  console.log("[bundle] Windows uses the NSIS installer: npm run desktop:installer");
  process.exit(0);
}
if (mode === "linux" || mode === "deb") buildDeb();
else if (mode === "darwin" || mode === "mac") buildMac();
else {
  console.error(`[bundle] unsupported platform ${process.platform}`);
  process.exit(1);
}

