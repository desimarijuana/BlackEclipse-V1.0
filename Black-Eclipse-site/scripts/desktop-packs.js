#!/usr/bin/env node
// Manage optional feature packs.
//
//   node scripts/desktop-packs.js list
//   node scripts/desktop-packs.js install <pack> [--target <app dir>]
//   node scripts/desktop-packs.js remove  <pack> [--target <app dir>]
//
// A pack is a set of Python packages that the harness imports *lazily*, so the
// app runs without them and gains the capability when the folder appears.
//
// Installing copies the pack into the target app's own site-packages. That is
// deliberate: `python-runtime.ts` sets `PYTHONPATH` to the app root, so an
// external directory would be ignored. The per-user install is writable, which
// is why this works without elevation.
//
// Target defaults to dist/BlackEclipse (the build tree). For an installed copy:
//   --target "%LOCALAPPDATA%\Programs\BlackEclipse"

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const PACKS_DIR = path.join(ROOT, "dist", "packs");
const DEFAULT_TARGET = path.join(ROOT, "dist", "BlackEclipse");

function manifest() {
  const file = path.join(PACKS_DIR, "manifest.json");
  if (!fs.existsSync(file)) {
    console.error("No pack manifest. Run `npm run desktop:package` first.");
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function sitePackages(target) {
  return path.join(target, "app", "scripts", "vendor", "python", "Lib", "site-packages");
}

function args() {
  const argv = process.argv.slice(2);
  const targetIndex = argv.indexOf("--target");
  let target = DEFAULT_TARGET;
  if (targetIndex !== -1) {
    target = argv[targetIndex + 1];
    argv.splice(targetIndex, 2);
  }
  return { command: argv[0], name: argv[1], target };
}

function list() {
  const { packs } = manifest();
  console.log("\nOptional packs\n");
  for (const pack of packs) {
    const mb = (pack.bytes / 1024 / 1024).toFixed(0);
    console.log(`  ${pack.name.padEnd(12)} ${String(mb).padStart(4)} MB   ${pack.packages.join(", ")}`);
  }
  console.log("\nInstall: node scripts/desktop-packs.js install <pack>\n");
}

function install(name, target) {
  const pack = manifest().packs.find((p) => p.name === name);
  if (!pack) {
    console.error(`Unknown pack "${name}". Try: list`);
    process.exit(1);
  }
  const source = path.join(PACKS_DIR, name, "site-packages");
  const dest = sitePackages(target);
  if (!fs.existsSync(dest)) {
    console.error(`No app at ${target} (expected ${dest}).`);
    process.exit(1);
  }
  fs.cpSync(source, dest, { recursive: true });
  console.log(`installed "${name}" (${pack.packages.join(", ")}) -> ${dest}`);
}

function remove(name, target) {
  const pack = manifest().packs.find((p) => p.name === name);
  if (!pack) {
    console.error(`Unknown pack "${name}". Try: list`);
    process.exit(1);
  }
  const dest = sitePackages(target);
  let removed = 0;
  for (const pkg of pack.packages) {
    const dir = path.join(dest, pkg);
    if (fs.existsSync(dir)) {
      fs.rmSync(dir, { recursive: true, force: true });
      removed += 1;
    }
  }
  console.log(`removed ${removed} package(s) for "${name}"`);
}

const { command, name, target } = args();
if (command === "list") list();
else if (command === "install" && name) install(name, target);
else if (command === "remove" && name) remove(name, target);
else {
  console.log("usage: node scripts/desktop-packs.js <list|install|remove> [pack] [--target <dir>]");
  process.exit(1);
}
