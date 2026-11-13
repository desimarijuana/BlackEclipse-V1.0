// Versioned desktop release artifacts and promotion pointers.
//
// Layout:
//   releases/<channel>/<buildId>/            immutable build copy + manifest.json
//   releases/<channel>/current.json          the build the channel serves
//   releases/<channel>/previous.json         the rollback target
//
// A release is only ever written into a temporary directory and renamed into
// place, so a half-copied build can never become current. Promotion validates
// the copy BEFORE the pointer moves; rollback swaps the two pointers.

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");

// Next's multi-GB cache and diagnostics are never part of a runtime payload.
const SKIP = new Set(["cache", "diagnostics", "standalone", "trace", ".build-hash"]);

function releaseRoot(channel) {
  return channel.releasesDir;
}

function pointerFile(channel, name) {
  return path.join(releaseRoot(channel), `${name}.json`);
}

function readBuildId(dir) {
  try {
    return fs.readFileSync(path.join(dir, "BUILD_ID"), "utf8").trim() || null;
  } catch {
    return null;
  }
}

/** A build `next start` can serve: id + routes manifest + server + static. */
function buildLooksComplete(dir) {
  if (!readBuildId(dir)) return false;
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(dir, "routes-manifest.json"), "utf8"));
    if (!manifest || typeof manifest !== "object") return false;
  } catch {
    return false;
  }
  if (!fs.existsSync(path.join(dir, "server"))) return false;
  if (!fs.existsSync(path.join(dir, "static"))) return false;
  // Next writes a per-build manifest under static/<buildId>/; its absence is
  // the signature of a truncated copy.
  const buildId = readBuildId(dir);
  return fs.existsSync(path.join(dir, "static", buildId));
}

function copyRuntime(from, to) {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    if (SKIP.has(entry.name)) continue;
    fs.cpSync(path.join(from, entry.name), path.join(to, entry.name), {
      recursive: true,
      force: true,
    });
  }
}

function readPointer(channel, name) {
  try {
    const info = JSON.parse(fs.readFileSync(pointerFile(channel, name), "utf8"));
    if (!info || typeof info.dir !== "string") return null;
    const dist = path.resolve(ROOT, info.dir);
    return { ...info, dist, valid: buildLooksComplete(dist) };
  } catch {
    return null;
  }
}

function writePointer(channel, name, info) {
  const file = pointerFile(channel, name);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(info, null, 2));
  fs.renameSync(temp, file);
}

module.exports = {
  ROOT,
  releaseRoot,
  pointerFile,
  readBuildId,
  buildLooksComplete,
  copyRuntime,
  readPointer,
  writePointer,
};
