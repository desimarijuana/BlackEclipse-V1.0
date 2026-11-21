// One answer to "which files did I touch?" for the gate scripts.
//
// WHY: `test:fast`, `verify` and anything else that narrows work by domain must
// agree on what "changed" means, or two commands will disagree about whether a
// change is covered. `git status --porcelain` is the only source that sees BOTH
// modified tracked files and new untracked ones (a brand-new test file is
// untracked, and `git diff` alone would miss it).
//
// Paths are returned relative to the app directory (`Black-Eclipse-site/`), even
// though git prints them relative to the repository root. Files outside the app
// are dropped: they are not this package's to test.
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const appPrefix = "Black-Eclipse-site/";

/**
 * @returns {{ ok: boolean, files: string[], reason?: string }}
 *   `ok: false` means the changed set is unknowable (not a git work tree), so
 *   callers must fall back to running everything rather than nothing.
 */
function changedFiles() {
  const status = spawnSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" });
  if (status.status !== 0) {
    return { ok: false, files: [], reason: "not a git work tree" };
  }

  const files = status.stdout
    .split("\n")
    .map((line) => line.slice(3).trim())
    .filter(Boolean)
    // A rename is reported as "old -> new"; only the destination exists.
    .map((line) => (line.includes(" -> ") ? line.split(" -> ")[1] : line))
    .map((file) => (file.startsWith(appPrefix) ? file.slice(appPrefix.length) : file))
    .filter((file) => !file.startsWith("Black-Eclipse-site/"));

  return { ok: true, files };
}

/** Files under `prefix` with one of `exts`, e.g. under("src/", ".ts", ".tsx"). */
function under(files, prefix, ...exts) {
  return files.filter((file) => file.startsWith(prefix) && exts.some((ext) => file.endsWith(ext)));
}

module.exports = { changedFiles, under, root };
