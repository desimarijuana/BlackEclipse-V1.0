#!/usr/bin/env node
// Assemble a runnable, self-contained Black Eclipse folder.
//
//   dist/BlackEclipse/
//     Black Eclipse.exe        Tauri shell
//     runtime/node.exe         bundled Node (no system Node required)
//     app/                     Next standalone payload + python + scripts
//       server.js
//       .next/  public/  node_modules/  python/  scripts/  config/
//     data/                    created at first run (%LOCALAPPDATA% in a real install)
//
// Run after `npm run desktop:payload` and `npm run desktop:build`.
//
// `--link` junctions the heavy trees instead of copying them. That makes a local
// smoke test take seconds instead of minutes; a real distributable must NOT use
// it (a junction cannot be shipped).
//
// The layout is dictated by the app, not by taste: `python-runtime.ts` resolves
// `python/harness` and its `.black-eclipse` locks from `process.cwd()`, so `app/`
// must be the process root and must be writable. That is why a packaged install
// is per-user, never Program Files.

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { ensureNode } = require("./desktop-runtime");
const { ensureSeedDatabase } = require("./lib/seed-db");
const { scrubAppState, assertNoLocalState } = require("./lib/scrub-app-state");

const ROOT = path.join(__dirname, "..");
const STANDALONE = path.join(ROOT, ".next-desktop", "standalone");
const OUT = path.join(ROOT, "dist", "BlackEclipse");
const DIST_PACKS = path.join(ROOT, "dist", "packs");
const APP = path.join(OUT, "app");
const SHELL_BIN = process.platform === "win32" ? "black-eclipse-desktop.exe" : "black-eclipse-desktop";
const SHELL = path.join(ROOT, "desktop", "src-tauri", "target", "release", SHELL_BIN);
const OUT_SHELL = process.platform === "win32" ? "Black Eclipse.exe" : "Black Eclipse";
const VENDOR_PY = path.join(ROOT, "scripts", "vendor", "python");
// Packs contain compiled wheels, so they are per target. The manifest records
// which target an archive belongs to; a downloader requests the matching one.
const TARGET = `${process.platform}-${process.arch}`;

const LINK = process.argv.includes("--link");

function fail(message) {
  console.error(`\n[package] ${message}\n`);
  process.exit(1);
}

function rmTree(dir) {
  // Antivirus/file-indexer handles and deep vendored-Python paths make a plain
  // recursive delete flaky; retry, then fall back to the extended-length prefix.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
      if (!fs.existsSync(dir)) return;
    } catch {}
    if (process.platform === "win32") {
      try {
        require("child_process").execFileSync(
          "cmd",
          ["/c", "rmdir", "/s", "/q", `\\\\?\\${path.resolve(dir)}`],
          { stdio: "ignore" }
        );
      } catch {}
    }
  }
  if (fs.existsSync(dir)) fail(`Could not clear ${path.relative(ROOT, dir)} (close any running Black Eclipse first).`);
}

function dirMB(dir) {
  let total = 0;
  const walk = (d) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) walk(p);
      else if (entry.isFile()) {
        try {
          total += fs.statSync(p).size;
        } catch {}
      }
    }
  };
  try {
    walk(dir);
  } catch {}
  return total / (1024 * 1024);
}

function copyTree(from, to, label) {
  if (!fs.existsSync(from)) {
    console.log(`  skip ${label} (missing: ${path.relative(ROOT, from)})`);
    return false;
  }
  if (LINK) {
    fs.mkdirSync(path.dirname(to), { recursive: true });
    try {
      fs.unlinkSync(to);
    } catch {}
    fs.symlinkSync(from, to, "junction");
    console.log(`  link ${label}`);
  } else {
    fs.cpSync(from, to, { recursive: true });
    console.log(`  copy ${label}`);
  }
  return true;
}

if (!fs.existsSync(path.join(STANDALONE, "server.js"))) {
  fail("No standalone payload. Run `npm run desktop:payload` first.");
}
if (!fs.existsSync(SHELL)) {
  fail("No shell binary. Run `npm run desktop:build` first.");
}

console.log(`Assembling ${path.relative(ROOT, OUT)}${LINK ? " (linked, local test only)" : ""}\n`);

rmTree(OUT);
rmTree(DIST_PACKS);
fs.mkdirSync(APP, { recursive: true });

// 1. The Next standalone payload. It already contains `.next-desktop/static`
// and `public/` (assembled by desktop-payload.js); copying them again here would
// recreate a stray `.next` tree.
copyTree(STANDALONE, APP, "payload -> app/");

// 2. The application root the runtime resolves against.
copyTree(path.join(ROOT, "python"), path.join(APP, "python"), "python/");
copyTree(path.join(ROOT, "config"), path.join(APP, "config"), "config/");
copyTree(path.join(ROOT, "skills"), path.join(APP, "skills"), "skills/");
copyTree(VENDOR_PY, path.join(APP, "scripts", "vendor", "python"), "vendored python");

// 3. Those trees are copied from the working checkout, so they still carry this
// machine's runtime state: the channel encryption key, the author's own agent
// session trajectories, Python caches and any stray vault. Strip it before the
// seed is generated, so the only database in the payload is seed/jdds.db.
// (The standalone payload prunes its own tree; these app-root copies land after
// that step, so they need their own pass.)
const scrub = scrubAppState(APP);
console.log(
  `  scrub local state: ${scrub.removed.length} path(s), ${(scrub.bytes / 1024 / 1024).toFixed(1)} MB`
);

// 4. Only the scripts the bootstrap actually needs — not the whole toolchain.
fs.mkdirSync(path.join(APP, "scripts"), { recursive: true });for (const file of ["desktop-server.js", "db-guard.js"]) {
  const from = path.join(ROOT, "scripts", file);
  if (fs.existsSync(from)) {
    fs.copyFileSync(from, path.join(APP, "scripts", file));
    console.log(`  copy scripts/${file}`);
  }
}
copyTree(path.join(ROOT, "scripts", "lib"), path.join(APP, "scripts", "lib"), "scripts/lib");

// 5. Prisma's generated client lives outside the traced tree.
const prismaGenerated = path.join(ROOT, "node_modules", ".prisma");
if (fs.existsSync(prismaGenerated)) {
  copyTree(prismaGenerated, path.join(APP, "node_modules", ".prisma"), "node_modules/.prisma");
}

// 5a. Optional native modules that Next's tracer misses. They are resolved only
// at runtime, so a traced build drops them and the feature degrades silently —
// pdfjs logs "Cannot load @napi-rs/canvas" and PDF rendering breaks.
for (const pkg of ["@napi-rs", "@img"]) {
  copyTree(
    path.join(ROOT, "node_modules", pkg),
    path.join(APP, "node_modules", pkg),
    `node_modules/${pkg}`
  );
}

// 5b. Compiled Python caches are regenerable and are the deepest paths in the
// tree — they are what pushes Windows past the 260-character limit during
// install. Remove them from the payload.
function prunePycache(dir) {
  let removed = 0;
  const walk = (d) => {
    let entries;
    try {
      entries = fs.readdirSync(d, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const p = path.join(d, entry.name);
      if (!entry.isDirectory()) continue;
      if (entry.name === "__pycache__") {
        try {
          fs.rmSync(p, { recursive: true, force: true });
          removed += 1;
        } catch {}
        continue;
      }
      walk(p);
    }
  };
  walk(dir);
  return removed;
}

const pycache = prunePycache(path.join(APP, "scripts", "vendor", "python"));
console.log(`  pruned ${pycache} __pycache__ directories`);

// 5c. First-run seed database: schema + the shared demo journal, so a packaged
// install opens populated instead of empty. See scripts/lib/seed-db.js.
ensureSeedDatabase({ appDir: APP, rootDir: ROOT, fail });

// 5c-2. Hard gate: a leaking installer is worse than a failed build.
assertNoLocalState(APP, fail);
console.log("  verified: no local state in the payload");

// 5d. Permanent junk: tests, metadata and caches that never run at runtime.
// Removing them cannot change behaviour — they are not imported.
function pruneJunk() {
  let mb = 0;
  const sizeOf = (p) => {
    try {
      const st = fs.statSync(p);
      if (st.isFile()) return st.size;
    } catch {
      return 0;
    }
    let total = 0;
    for (const e of fs.readdirSync(p, { withFileTypes: true })) total += sizeOf(path.join(p, e.name));
    return total;
  };

  const remove = (p) => {
    if (!fs.existsSync(p)) return;
    mb += sizeOf(p) / (1024 * 1024);
    fs.rmSync(p, { recursive: true, force: true });
  };

  // Harness tests — 52 MB of pytest files that never execute in production.
  remove(path.join(APP, "python", "tests"));

  // Python package test suites and distribution metadata.
  const sitePackages = path.join(APP, "scripts", "vendor", "python", "Lib", "site-packages");
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const p = path.join(dir, entry.name);
      if (!entry.isDirectory()) continue;
      if (entry.name === "tests" || entry.name === "test") {
        remove(p);
        continue;
      }
      // NOTE: `*.dist-info` is deliberately KEPT. It costs ~7 MB, but packages
      // such as plotly call `importlib.metadata.version(__name__)` at import
      // time and fail with PackageNotFoundError when it is gone.
      walk(p);
    }
  };
  walk(sitePackages);

  // TypeScript is a build tool; the compiled server never requires it.
  remove(path.join(APP, "node_modules", "typescript"));

  console.log(`  pruned junk: ${mb.toFixed(0)} MB (tests, metadata, build-only modules)`);
}

pruneJunk();

// 5e. Optional packs. Every package here is imported lazily inside a function
// (`# noqa: PLC0415`), so the harness already runs without it. Moving them out of
// the core ships a smaller installer and lets onboarding install them later.
// `comtypes` deliberately stays in core: it is touched during the boot sweep.
const PACKS = {
  browser: ["playwright"],
  ml: ["xgboost", "sklearn", "scipy", "scipy.libs"],
  documents: ["pymupdf"],
  computer: ["winsdk"],
  charts: ["plotly", "matplotlib"],
};

function buildPacks() {
  const sitePackages = path.join(APP, "scripts", "vendor", "python", "Lib", "site-packages");
  const packsRoot = path.join(DIST_PACKS);
  fs.mkdirSync(packsRoot, { recursive: true });

  const manifest = [];

  for (const [name, packages] of Object.entries(PACKS)) {
    const packDir = path.join(packsRoot, name);
    const dest = path.join(packDir, "site-packages");
    fs.mkdirSync(dest, { recursive: true });

    let moved = 0;
    for (const pkg of packages) {
      const from = path.join(sitePackages, pkg);
      if (!fs.existsSync(from)) continue;
      fs.renameSync(from, path.join(dest, pkg));
      moved += 1;
    }

    if (moved === 0) {
      fs.rmSync(packDir, { recursive: true, force: true });
      continue;
    }

    const bytes = (() => {
      let total = 0;
      const walk = (d) => {
        for (const e of fs.readdirSync(d, { withFileTypes: true })) {
          const p = path.join(d, e.name);
          if (e.isDirectory()) walk(p);
          else total += fs.statSync(p).size;
        }
      };
      walk(packDir);
      return total;
    })();

    manifest.push({
      name,
      packages,
      bytes,
      path: `packs/${name}`,
      target: TARGET,
    });
    console.log(`  pack ${name}: ${(bytes / 1024 / 1024).toFixed(0)} MB (${packages.join(", ")})`);
  }

  fs.writeFileSync(
    path.join(packsRoot, "manifest.json"),
    JSON.stringify({ target: TARGET, packs: manifest }, null, 2)
  );
  console.log(`  pack manifest: ${manifest.length} packs for ${TARGET}`);

  // Archives for distribution. GitHub hashes and `winget` both want a file, and a
  // stub installer cannot fetch a folder. `tar -a` produces a real zip on Windows.
  const { execFileSync } = require("child_process");
  const crypto = require("crypto");
  const entries = [];

  for (const pack of manifest) {
    const zipPath = path.join(packsRoot, `${pack.name}.zip`);
    try {
      fs.rmSync(zipPath, { force: true });
      execFileSync("tar", ["-a", "-cf", zipPath, "-C", path.join(packsRoot, pack.name), "."], {
        stdio: "ignore",
      });
      const sha256 = crypto.createHash("sha256").update(fs.readFileSync(zipPath)).digest("hex");
      const zipBytes = fs.statSync(zipPath).size;
      entries.push({ ...pack, zip: `packs/${pack.name}.zip`, zipBytes, sha256 });
      console.log(`  pack ${pack.name}.zip: ${(zipBytes / 1024 / 1024).toFixed(0)} MB`);
    } catch (err) {
      console.log(`  pack ${pack.name}.zip: FAILED (${err.message})`);
    }
  }

  fs.writeFileSync(
    path.join(packsRoot, "manifest.json"),
    JSON.stringify({ target: TARGET, packs: entries }, null, 2)
  );
}

buildPacks();

// Runtime state written by a local test run must never ship: logs contain local
// paths, and the prefs file is per-machine.
fs.rmSync(path.join(APP, ".black-eclipse"), { recursive: true, force: true });
console.log("  cleared app/.black-eclipse (runtime state)");

// 6. Runtime + shell.
fs.mkdirSync(path.join(OUT, "runtime"), { recursive: true });
// Platform-correct Node: an archive from nodejs.org, not the build machine's
// binary. `--from-system` is a local shortcut for same-platform builds.
ensureNode(path.join(OUT, "runtime"), { fromSystem: process.argv.includes("--from-system") });
console.log(`  runtime/node${process.platform === "win32" ? ".exe" : ""}`);

// 6b. Give the two runtime executables inside the install OUR identity. Windows
// takes each process's Task Manager icon and display name from the executable it
// runs, so an unbranded install shows "Node.js JavaScript Runtime" and "Python"
// next to the app. Cosmetics only — the binaries behave identically.
const { brandPackagedRuntime } = require("./brand-runtime");
brandPackagedRuntime(OUT);

fs.copyFileSync(SHELL, path.join(OUT, OUT_SHELL));
try {
  fs.chmodSync(path.join(OUT, OUT_SHELL), 0o755);
} catch {}
console.log(`  copy ${OUT_SHELL}`);

console.log("\nResult:");
console.log(`  app     ${dirMB(APP).toFixed(0)} MB`);
console.log(`  total   ${dirMB(OUT).toFixed(0)} MB`);
console.log(`\nRun: "${path.join(OUT, OUT_SHELL)}"`);

if (LINK) {
  console.log("\nThis build uses junctions and cannot be shipped. Re-run without --link for a release folder.");
}
