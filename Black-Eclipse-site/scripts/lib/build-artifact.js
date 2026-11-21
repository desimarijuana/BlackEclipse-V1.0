// ── Signed prebuilt build artifacts ─────────────────────────────────────────
// The release is a COMPILED artifact, not a tag to rebuild on the user's
// machine. This module is the one place that knows how to take the signed
// `builds` entry from a verified manifest and turn it into a serviceable build
// directory:
//
//   download (streamed, hashed) → verify size + sha256 → extract into a private
//   staging dir (zip-slip rejected) → locate/validate the build → hand the path
//   to `desktop-promote.js --from`.
//
// Why this exists: the checkout-based updater refused whenever the working tree
// was dirty, and every release touches the changelog (a date, some text), so the
// update was blocked on the maintainer's own machine nearly every time. Nothing
// here reads git at all.
//
// Safety invariants (do not relax):
//   * the URL and digest come from the SIGNED manifest; a mismatch deletes the
//     download and installs nothing;
//   * extraction refuses absolute paths and `..` segments;
//   * a build is only "serviceable" if `buildLooksComplete()` accepts it, and
//     the archive's advertised BUILD_ID must match the extracted one.

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { Readable, Transform } = require("stream");
const { pipeline } = require("stream/promises");
const { spawnSync } = require("child_process");

const { buildLooksComplete, readBuildId } = require("./desktop-release");

/**
 * Pick the build for this host: an exact `<platform>-<arch>` entry wins over
 * the platform-independent `any` entry (a Next build is JS, so `any` is normal).
 */
function assetForPlatform(builds, platform) {
  if (!builds || typeof builds !== "object") return null;
  const keys = [platform, "any"];
  for (const key of keys) {
    const asset = builds[key];
    if (asset && asset.url && asset.sha256) return { key, asset };
  }
  return null;
}

function sha256File(file) {
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const chunk = Buffer.allocUnsafe(4 * 1024 * 1024);
  try {
    for (;;) {
      const read = fs.readSync(fd, chunk, 0, chunk.length, null);
      if (read <= 0) break;
      hash.update(chunk.subarray(0, read));
    }
  } finally {
    fs.closeSync(fd);
  }
  return hash.digest("hex");
}

/** sha256 of the release's package-lock.json, or null when there is none. */
function lockHash(root) {
  try {
    return sha256File(path.join(root, "package-lock.json"));
  } catch {
    return null;
  }
}

/**
 * Stream a URL to `dest`, hashing on the way. Nothing is kept unless both the
 * signed digest and (when present) the signed size match.
 *
 * `onBeat` is called periodically so a slow download can still write a job
 * heartbeat; without it the UI would read a live download as a dead run.
 */
async function downloadVerified(url, dest, { sha256, size, onBeat } = {}) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const tmp = `${dest}.part`;
  fs.rmSync(tmp, { force: true });

  let response;
  try {
    response = await fetch(url, {
      headers: { accept: "application/octet-stream", "cache-control": "no-cache" },
      redirect: "follow",
      // Large artifact, slow link, no deadline on progress: the heartbeat
      // covers liveness, not this timeout.
      signal: AbortSignal.timeout(30 * 60 * 1000),
    });
  } catch {
    throw new Error("Could not reach the release download.");
  }
  if (!response.ok || !response.body) {
    throw new Error(`The release download returned HTTP ${response.status}.`);
  }

  const hash = crypto.createHash("sha256");
  let total = 0;
  const meter = new Transform({
    transform(chunk, _encoding, callback) {
      total += chunk.length;
      if (size && total > size) {
        callback(new Error("The downloaded file is larger than the signed size."));
        return;
      }
      hash.update(chunk);
      if (onBeat && total % (4 * 1024 * 1024) < chunk.length) onBeat();
      callback(null, chunk);
    },
  });

  const beat = onBeat ? setInterval(onBeat, 30_000) : null;
  try {
    await pipeline(Readable.fromWeb(response.body), meter, fs.createWriteStream(tmp));
  } catch (err) {
    fs.rmSync(tmp, { force: true });
    throw err;
  } finally {
    if (beat) clearInterval(beat);
  }

  const digest = hash.digest("hex");
  if (digest !== String(sha256).toLowerCase()) {
    fs.rmSync(tmp, { force: true });
    throw new Error(
      "The downloaded build failed its signed checksum and was deleted. Nothing was installed.",
    );
  }
  if (size && total !== size) {
    fs.rmSync(tmp, { force: true });
    throw new Error(
      `The downloaded build is ${total} bytes but the signed release says ${size}. Nothing was installed.`,
    );
  }
  fs.renameSync(tmp, dest);
  return { bytes: total, sha256: digest };
}

/** `unzip` where it exists, otherwise bsdtar (Windows 10+, macOS) — never GNU tar. */
function listArchive(archive) {
  const unzip = spawnSync("unzip", ["-Z1", archive], { encoding: "utf8", windowsHide: true });
  if (unzip.status === 0) return { tool: "unzip", entries: splitLines(unzip.stdout) };
  const tar = spawnSync("tar", ["-tf", archive], { encoding: "utf8", windowsHide: true });
  if (tar.status === 0) return { tool: "tar", entries: splitLines(tar.stdout) };
  throw new Error(
    "Cannot read the release archive: neither `unzip` nor a zip-capable `tar` is available.",
  );
}

function splitLines(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Reject absolute paths, `..` segments and drive letters before extracting. */
function assertSafeEntries(entries) {
  for (const entry of entries) {
    const normalized = entry.replace(/\\/g, "/");
    if (!normalized) continue;
    if (normalized.startsWith("/") || /^[a-zA-Z]:/.test(normalized)) {
      throw new Error(`The release archive contains an absolute path (${entry}); refusing to extract it.`);
    }
    const parts = normalized.split("/");
    if (parts.includes("..")) {
      throw new Error(`The release archive escapes its own directory (${entry}); refusing to extract it.`);
    }
  }
}

/**
 * Extract a zip into `destDir`. The archive is expected to contain `.next/` at
 * its root (one optional wrapping folder is tolerated).
 */
function extractArchive(archive, destDir) {
  const { tool, entries } = listArchive(archive);
  assertSafeEntries(entries);
  fs.rmSync(destDir, { recursive: true, force: true });
  fs.mkdirSync(destDir, { recursive: true });
  const result =
    tool === "unzip"
      ? spawnSync("unzip", ["-q", "-o", archive, "-d", destDir], { stdio: "inherit", windowsHide: true })
      : spawnSync("tar", ["-xf", archive, "-C", destDir], { stdio: "inherit", windowsHide: true });
  if (result.status !== 0) {
    throw new Error(`Could not extract the release archive (${tool} exited ${result.status}).`);
  }
  return tool;
}

/**
 * The serviceable build directory inside `dir`: `dir` itself, `dir/<one
 * folder>`, or `<folder>/.next`, whichever `buildLooksComplete()` accepts.
 */
function findBuildRoot(dir) {
  const candidates = [dir];
  for (const entry of safeReaddir(dir)) {
    const full = path.join(dir, entry);
    if (!isDir(full)) continue;
    candidates.push(full, path.join(full, ".next"));
  }
  for (const candidate of candidates) {
    if (buildLooksComplete(candidate)) return candidate;
  }
  return null;
}

function safeReaddir(dir) {
  try {
    return fs.readdirSync(dir);
  } catch {
    return [];
  }
}

function isDir(target) {
  try {
    return fs.statSync(target).isDirectory();
  } catch {
    return false;
  }
}

/**
 * Turn a downloaded archive into a validated build directory.
 *
 * Returns `{ buildDir, buildId }`; throws with an actionable message when the
 * archive is not a complete, matching build. The `buildId` the manifest names
 * must equal the one in the archive — otherwise the artifact is not the release
 * the signature described.
 */
function unpackBuild(archive, destDir, expected = {}) {
  extractArchive(archive, destDir);
  const buildDir = findBuildRoot(destDir);
  if (!buildDir) {
    throw new Error(
      "The downloaded build is incomplete (no BUILD_ID / routes manifest / static). Nothing was installed.",
    );
  }
  const buildId = readBuildId(buildDir);
  if (expected.buildId && buildId !== expected.buildId) {
    throw new Error(
      `The downloaded build is ${buildId || "missing BUILD_ID"}, but the signed release says ` +
        `${expected.buildId}. Nothing was installed.`,
    );
  }
  return { buildDir, buildId };
}

module.exports = {
  assetForPlatform,
  sha256File,
  lockHash,
  downloadVerified,
  extractArchive,
  findBuildRoot,
  unpackBuild,
  assertSafeEntries,
};
