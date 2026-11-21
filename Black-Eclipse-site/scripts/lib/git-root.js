// ── Locate the enclosing git work tree ───────────────────────────────────────
// The app lives in `Black-Eclipse-site/`, but the repository root is its PARENT
// (`Black-Eclipse-site/.git` does not exist). A bare `existsSync(root/.git)`
// therefore misread this checkout as a packaged install and refused in-app
// updates with "This installed build cannot update in place."
//
// Walk up from the app root instead. A packaged install ships `server.js` in
// the payload root and has no work tree above it; that marker still wins, so an
// install that happens to sit inside some unrelated repository is never
// mistaken for a checkout.

const fs = require("fs");
const path = require("path");

/**
 * The nearest ancestor (including `start`) that holds a `.git` entry, or null.
 * Worktrees use a `.git` FILE, so this must not require a directory.
 */
function findGitRoot(start) {
  let dir = path.resolve(start);
  for (;;) {
    try {
      if (fs.existsSync(path.join(dir, ".git"))) return dir;
    } catch {
      return null;
    }
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

/** Is `root` a source checkout the git-based updater can move? */
function isSourceCheckout(root) {
  if (!root) return false;
  try {
    // The standalone payload marker means "packaged", even inside a repo.
    if (fs.existsSync(path.join(root, "server.js"))) return false;
  } catch {
    return false;
  }
  return findGitRoot(root) !== null;
}

module.exports = { findGitRoot, isSourceCheckout };
