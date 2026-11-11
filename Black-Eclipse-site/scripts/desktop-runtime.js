#!/usr/bin/env node
// Provide the platform-appropriate runtime for a packaged install.
//
// Why this exists: the payload used to copy the *build machine's* `node.exe`.
// That is fine on Windows and wrong everywhere else — a macOS payload needs a
// darwin arm64 binary, a Linux payload needs an elf. The archive is fetched from
// nodejs.org, verified against their published SHASUMS256.txt when reachable,
// and cached so repeat builds do not re-download.
//
// `curl` and `tar` ship with Windows 10+, macOS and every mainstream Linux, so
// this needs no dependency.

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const CACHE = path.join(ROOT, ".black-eclipse", "runtime-cache");
const NODE_VERSION = process.env.BE_NODE_VERSION || process.versions.node;

/** Map the current platform/arch to the archive nodejs.org publishes. */
function nodeArchive() {
  const version = `v${NODE_VERSION}`;
  const platform = process.platform;
  const arch = process.arch;

  if (platform === "win32") {
    if (arch !== "x64" && arch !== "arm64") throw new Error(`unsupported win32 arch ${arch}`);
    return { name: `node-${version}-win-${arch}`, ext: "zip" };
  }
  if (platform === "darwin") {
    if (arch !== "x64" && arch !== "arm64") throw new Error(`unsupported darwin arch ${arch}`);
    return { name: `node-${version}-darwin-${arch}`, ext: "tar.gz" };
  }
  if (platform === "linux") {
    if (arch !== "x64" && arch !== "arm64") throw new Error(`unsupported linux arch ${arch}`);
    return { name: `node-${version}-linux-${arch}`, ext: "tar.xz" };
  }
  throw new Error(`unsupported platform ${platform}`);
}

function run(cmd, args, options = {}) {
  const result = spawnSync(cmd, args, { stdio: options.stdio || "inherit", ...options });
  if (result.status !== 0) {
    throw new Error(`${cmd} ${args.join(" ")} failed (exit ${result.status})`);
  }
  return result;
}

function download(url, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  run("curl", ["-fsSL", "--retry", "3", "-o", dest, url], { stdio: "ignore" });
}

/**
 * Ensure `<targetDir>/node[.exe]` exists and return its path.
 * `fromSystem` copies the running interpreter instead (the old behaviour) and is
 * only correct when the target platform equals the build platform.
 */
function ensureNode(targetDir, { fromSystem = false } = {}) {
  fs.mkdirSync(targetDir, { recursive: true });
  const binName = process.platform === "win32" ? "node.exe" : "node";
  const dest = path.join(targetDir, binName);

  if (fromSystem) {
    fs.copyFileSync(process.execPath, dest);
    try {
      fs.chmodSync(dest, 0o755);
    } catch {}
    return dest;
  }

  const { name, ext } = nodeArchive();
  const archive = path.join(CACHE, `${name}.${ext}`);
  const extracted = path.join(CACHE, name);

  if (!fs.existsSync(archive)) {
    const url = `https://nodejs.org/dist/v${NODE_VERSION}/${name}.${ext}`;
    console.log(`  runtime: downloading ${name}.${ext} (${NODE_VERSION})`);
    download(url, archive);

    // Best effort: nodejs.org publishes one hash list per release.
    try {
      const sumsFile = path.join(CACHE, `SHASUMS256-${NODE_VERSION}.txt`);
      download(`https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt`, sumsFile);
      const expected = fs
        .readFileSync(sumsFile, "utf8")
        .split("\n")
        .map((line) => line.trim().split(/\s+/))
        .find(([, file]) => file === `${name}.${ext}`);
      if (expected && expected[0]) {
        const actual = require("crypto")
          .createHash("sha256")
          .update(fs.readFileSync(archive))
          .digest("hex");
        if (actual !== expected[0]) {
          fs.rmSync(archive, { force: true });
          throw new Error(`checksum mismatch for ${name}.${ext}`);
        }
        console.log("  runtime: checksum verified");
      }
    } catch (err) {
      if (/checksum mismatch/.test(String(err.message))) throw err;
      console.log(`  runtime: checksum skipped (${err.message})`);
    }
  } else {
    console.log(`  runtime: using cached ${name}.${ext}`);
  }

  if (!fs.existsSync(extracted)) {
    fs.rmSync(extracted, { recursive: true, force: true });
    fs.mkdirSync(extracted, { recursive: true });
    run("tar", ["-xf", archive, "-C", extracted], { stdio: "ignore" });
  }

  const source = path.join(extracted, name, "bin", binName);
  const flat = path.join(extracted, name, binName);
  const resolved = fs.existsSync(source) ? source : flat;
  if (!fs.existsSync(resolved)) throw new Error(`node binary not found in ${name}`);

  fs.copyFileSync(resolved, dest);
  try {
    fs.chmodSync(dest, 0o755);
  } catch {}
  return dest;
}

module.exports = { ensureNode, nodeArchive, NODE_VERSION };

if (require.main === module) {
  const target = process.argv[2] || path.join(ROOT, "dist", "BlackEclipse", "runtime");
  const fromSystem = process.argv.includes("--from-system");
  const bin = ensureNode(target, { fromSystem });
  console.log(`${bin}`);
}
