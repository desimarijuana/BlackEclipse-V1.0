#!/usr/bin/env node
// Build the DEV Tauri shell as a separate binary.
//
// Stable and Dev must be able to run at the same time. Tauri's single-instance
// guard is keyed by the app identifier, which is compiled in — so the Dev shell
// needs its OWN identifier, not just another port. `TAURI_CONFIG` merges a JSON
// overlay into `tauri.conf.json` at build time; the overlay below changes only
// the product name + identifier, leaving windows/icons/capabilities shared.
//
// Output: desktop/src-tauri/target-dev/debug/black-eclipse-desktop.exe
// (a separate target dir so it never overwrites the stable build).

const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const MANIFEST = path.join(ROOT, "desktop", "src-tauri", "Cargo.toml");
const TARGET_DIR = path.join(ROOT, "desktop", "src-tauri", "target-dev");

const overlay = {
  productName: "Black Eclipse Dev",
  identifier: "com.blackeclipse.desktop.dev",
};

console.log("[desktop:shell:dev] building separate Dev shell (identifier com.blackeclipse.desktop.dev)");
const result = spawnSync(
  "cargo",
  ["build", "--manifest-path", MANIFEST, "--target-dir", TARGET_DIR],
  {
    cwd: ROOT,
    stdio: "inherit",
    windowsHide: true,
    env: { ...process.env, TAURI_CONFIG: JSON.stringify(overlay) },
  },
);

if (result.error) {
  console.error(`[desktop:shell:dev] could not run cargo: ${result.error.message}`);
  process.exit(1);
}
if (result.status !== 0) {
  console.error(`[desktop:shell:dev] cargo build failed with exit ${result.status}`);
  process.exit(result.status || 1);
}

const exe = path.join(
  TARGET_DIR,
  "debug",
  process.platform === "win32" ? "black-eclipse-desktop.exe" : "black-eclipse-desktop",
);
console.log(`[desktop:shell:dev] built ${path.relative(ROOT, exe)}`);
