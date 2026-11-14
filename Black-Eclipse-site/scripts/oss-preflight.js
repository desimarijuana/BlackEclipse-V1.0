#!/usr/bin/env node
/**
 * Open-source publication preflight.
 *
 * `npm run check:all` answers "is this tree releasable?". This answers a
 * different question: "is this repository safe to make PUBLIC?".
 *
 * It is deliberately NOT part of `check:all`. A private working repository is
 * allowed to carry the failures below (for example, a `jdds.db` committed
 * before it became untracked). Run it before flipping visibility, and after the
 * history rewrite, to prove the public snapshot is clean.
 *
 *   node scripts/oss-preflight.js          # fail on blockers, report warnings
 *   node scripts/oss-preflight.js --json   # machine-readable result
 *
 * Exit 1 means: do not publish yet.
 */
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const siteRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(siteRoot, "..");
const asJson = process.argv.includes("--json");

const failures = [];
const warnings = [];
const notes = [];

function fail(message, fix) {
  failures.push({ message, fix });
}

function warn(message, fix) {
  warnings.push({ message, fix });
}

function git(args, options = {}) {
  return execFileSync("git", args, {
    cwd: repoRoot,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    ...options,
  });
}

function safeGit(args) {
  try {
    return git(args);
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// 1. No secret-bearing artifacts are tracked at HEAD.
// ---------------------------------------------------------------------------
const tracked = safeGit(["ls-files"]).split("\n").filter(Boolean);
const bannedArtifact =
  /(^|\/)(\.env(\.[^/]+)?|\.connector-key|mcp-servers\.json|.*\.(db|db-wal|db-shm|pem|pfx|key|p12))$/i;

for (const file of tracked) {
  if (file === "Black-Eclipse-site/.env.example") continue;
  if (bannedArtifact.test(file)) {
    fail(
      `tracked secret/state artifact: ${file}`,
      "Untrack it (git rm --cached), add it to .gitignore, and rotate anything it contained."
    );
  }
}

// ---------------------------------------------------------------------------
// 2. The community files a public repository is expected to have.
// ---------------------------------------------------------------------------
const requiredFiles = [
  "LICENSE",
  "README.md",
  "CONTRIBUTING.md",
  "SECURITY.md",
  "CODE_OF_CONDUCT.md",
  "CODEOWNERS",
  ".github/PULL_REQUEST_TEMPLATE.md",
  ".github/ISSUE_TEMPLATE/bug_report.yml",
  ".github/ISSUE_TEMPLATE/feature_request.yml",
  ".github/ISSUE_TEMPLATE/config.yml",
];

for (const file of requiredFiles) {
  if (!fs.existsSync(path.join(repoRoot, file))) {
    fail(`missing community file: ${file}`, "Add it before making the repository public.");
  }
}

// ---------------------------------------------------------------------------
// 3. Package metadata points at the real repository.
// ---------------------------------------------------------------------------
try {
  const pkg = JSON.parse(
    fs.readFileSync(path.join(siteRoot, "package.json"), "utf8")
  );
  if (!pkg.repository || !pkg.repository.url) {
    fail("package.json has no repository.url", "Add the canonical GitHub URL.");
  }
  if (!pkg.homepage) {
    warn("package.json has no homepage", "Add the README URL so npm links back.");
  }
  if (!pkg.bugs || !pkg.bugs.url) {
    warn("package.json has no bugs.url", "Add the issue tracker URL.");
  }
  if (pkg.private === true) {
    notes.push(
      "package.json private:true — correct for an app; it only blocks `npm publish`, not GitHub visibility."
    );
  }
} catch (error) {
  fail(`cannot read Black-Eclipse-site/package.json: ${error.message}`, "Fix the JSON.");
}

// ---------------------------------------------------------------------------
// 4. History: state and personal paths are the two things a public clone leaks.
// ---------------------------------------------------------------------------
const everAdded = safeGit([
  "log",
  "--all",
  "--format=",
  "--name-only",
  "--diff-filter=A",
])
  .split("\n")
  .map((line) => line.trim())
  .filter(Boolean);

const historyDatabases = [...new Set(everAdded.filter((f) => /(^|\/).*\.db$/i.test(f)))];
if (historyDatabases.length > 0) {
  fail(
    `git history still contains database snapshot(s): ${historyDatabases.join(", ")}`,
    "Publish from a rewritten history (git filter-repo) or a fresh squashed repository. A seed DB can contain a real journal."
  );
}

const historySecrets = [
  ...new Set(
    everAdded
      .filter((f) =>
        /(^|\/)(\.env(\.[^/]+)?|\.connector-key|mcp-servers\.json)$/i.test(f)
      )
      // `.env.example` is a documentation template, not a secret.
      .filter((f) => !/\.env\.example$/i.test(f))
  ),
];
if (historySecrets.length > 0) {
  fail(
    `git history still contains secret-bearing path(s): ${historySecrets.join(", ")}`,
    "Scrub history and rotate any credential that was ever committed."
  );
}

// Absolute home-directory paths in tracked text files. These leak a username
// and often a project name; they are not credentials, but they do not belong in
// a public tree.
// Match one or two literal backslashes (plain text and JSON-escaped paths).
const personalPathPattern = String.raw`([A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}|/Users/)[A-Za-z0-9._-]+`;
// Obvious fixtures/placeholders are not leaks. `msi` is matched
// case-sensitively so a test fixture does not hide a real uppercase user path.
const placeholderUser =
  /[\\/]{1,2}Users[\\/]{1,2}(me|x|msi|user|username|Public|test|example)(?![A-Za-z0-9._-])/;
const personalPathHits = [
  ...new Set(
    safeGit(["grep", "-I", "-n", "-E", personalPathPattern, "--", "."])
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        const [file, , ...rest] = line.split(":");
        return { file, content: rest.join(":") };
      })
      .filter((hit) => !placeholderUser.test(hit.content))
      .map((hit) => hit.file)
  ),
];

if (personalPathHits.length > 0) {
  warn(
    `tracked file(s) contain an absolute home-directory path: ${personalPathHits.join(", ")}`,
    "Replace with a relative path or <user> placeholder, or scrub it in the public history."
  );
}

// A personal (non-noreply, non-project) author email is public the moment the
// history is public.
const authors = [
  ...new Set(
    safeGit(["log", "--all", "--format=%ae"])
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
  ),
];
const personalAuthors = authors.filter(
  (email) =>
    !/@users\.noreply\.github\.com$/i.test(email) &&
    !/@blackeclipse\.com$/i.test(email) &&
    !/\[bot\]@/i.test(email)
);
if (personalAuthors.length > 0) {
  warn(
    `commit author email(s) will be public: ${personalAuthors.join(", ")}`,
    "Rewriting history is the only fix; otherwise accept that they are published."
  );
}

// ---------------------------------------------------------------------------
// 5. The tree-level secret scan (same one the release gate runs).
// ---------------------------------------------------------------------------
try {
  execFileSync(process.execPath, [path.join(siteRoot, "scripts", "scan-secrets.js")], {
    cwd: siteRoot,
    stdio: asJson ? "pipe" : "inherit",
  });
} catch {
  fail(
    "scripts/scan-secrets.js failed",
    "A tracked file looks like a secret; run `npm run check:secrets` for the path."
  );
}

// ---------------------------------------------------------------------------
// 6. Advisory: documentation drift that makes a public repo look abandoned.
// ---------------------------------------------------------------------------
try {
  const pkg = JSON.parse(
    fs.readFileSync(path.join(siteRoot, "package.json"), "utf8")
  );
  const readme = fs.readFileSync(path.join(repoRoot, "README.md"), "utf8");
  if (pkg.version && !readme.includes(pkg.version)) {
    warn(
      `README.md does not mention the current version (${pkg.version})`,
      "Update the release paragraph so the public landing page is not stale."
    );
  }
} catch {
  // A missing README is already a failure above.
}

// ---------------------------------------------------------------------------
// Report.
// ---------------------------------------------------------------------------
const result = {
  ok: failures.length === 0,
  failures: failures.length,
  warnings: warnings.length,
  details: { failures, warnings, notes },
};

if (asJson) {
  console.log(JSON.stringify(result, null, 2));
} else {
  for (const note of notes) console.log(`[oss] note   ${note}`);
  for (const item of warnings) {
    console.log(`[oss] WARN   ${item.message}`);
    if (item.fix) console.log(`             fix: ${item.fix}`);
  }
  for (const item of failures) {
    console.log(`[oss] FAIL   ${item.message}`);
    if (item.fix) console.log(`             fix: ${item.fix}`);
  }
  if (failures.length === 0) {
    console.log(
      `\n[oss] public-release preflight PASS - ${warnings.length} warning(s).`
    );
  } else {
    console.log(
      `\n[oss] public-release preflight FAIL - ${failures.length} blocker(s), ${warnings.length} warning(s). Do not publish yet.`
    );
  }
}

process.exit(failures.length === 0 ? 0 : 1);
