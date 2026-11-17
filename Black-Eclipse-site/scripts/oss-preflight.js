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

/** Refs (local/remote/tags) from which `sha` is reachable. */
function refsContaining(sha) {
  if (!sha) return [];
  return [
    ...new Set(
      safeGit([
        "for-each-ref",
        "--contains",
        sha,
        "--format=%(refname:short)",
        "refs/heads",
        "refs/remotes",
        "refs/tags",
      ])
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
    ),
  ];
}

/** The newest commit that touched `file`, expressed as the refs that expose it. */
function refsForPath(file) {
  const sha = safeGit(["log", "--all", "-1", "--format=%H", "--", file]).trim();
  return refsContaining(sha);
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
  "THIRD-PARTY-NOTICES.md",
  "sbom.cdx.json",
];

for (const file of requiredFiles) {
  if (!fs.existsSync(path.join(repoRoot, file))) {
    fail(`missing community file: ${file}`, "Add it before making the repository public.");
  }
}

// The dependency inventory is a release artifact, not a nicety: an SBOM that
// predates the lockfiles is a publication blocker, the same as a missing
// licence. The generator owns the comparison.
try {
  execFileSync(process.execPath, [path.join(__dirname, "generate-sbom.js"), "--check"], {
    cwd: repoRoot,
    stdio: "pipe",
  });
} catch {
  fail(
    "sbom.cdx.json / THIRD-PARTY-NOTICES.md are missing or stale",
    "Run `npm run sbom` from Black-Eclipse-site, then re-run the preflight."
  );
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
  // Name the refs, not just the file: after a rewrite the mainline is often
  // already clean and the only remaining exposure is a stale branch. That
  // distinction is the difference between "redo the whole rewrite" and
  // "delete twelve branches".
  const dbRefs = [...new Set(historyDatabases.flatMap(refsForPath))];
  const mainClean = historyDatabases.every(
    (file) => !safeGit(["log", "main", "-1", "--format=%H", "--", file]).trim()
  );
  const where = dbRefs.length ? ` — reachable from: ${dbRefs.join(", ")}` : "";
  const mainState = mainClean
    ? " `main` and the tags are clean; these refs are the remaining exposure."
    : "";
  fail(
    `git history still contains database snapshot(s): ${historyDatabases.join(", ")}${where}.${mainState}`,
    dbRefs.length
      ? `Delete the listed refs (git push origin --delete <ref>), git fetch --prune, then re-scan. If a cached PR still reaches them, publish from a fresh repository. A seed DB can contain a real journal.`
      : "Publish from a rewritten history (git filter-repo) or a fresh squashed repository. A seed DB can contain a real journal."
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
  // Same evidence rule as the database check: name where the address is still
  // reachable so the operator knows whether a rewrite or a ref deletion fixes it.
  const wanted = new Set(personalAuthors);
  const refsByEmail = new Map();
  for (const row of safeGit(["log", "--all", "--format=%H%x00%ae"]).split("\n")) {
    const [sha, email] = row.split("\0");
    if (!sha || !wanted.has((email || "").trim())) continue;
    if (!refsByEmail.has(email.trim())) refsByEmail.set(email.trim(), refsContaining(sha));
  }
  const detail = personalAuthors
    .map((email) => {
      const refs = refsByEmail.get(email) || [];
      return refs.length ? `${email} (refs: ${refs.join(", ")})` : email;
    })
    .join("; ");
  warn(
    `commit author email(s) will be public: ${detail}`,
    "If every listed ref is a stale branch, deleting it removes the address. Otherwise rewriting history is the only fix, or accept that it is published."
  );
}

// ---------------------------------------------------------------------------
// 5. Server-side refs: GitHub serves refs/pull/* that no local scan can see.
// ---------------------------------------------------------------------------
// One evaluation for both "audit ran and exited 0" and "audit ran and exited 1
// because it found something" - the JSON is printed either way.
function consumeRemoteAudit(raw) {
  const audit = JSON.parse(raw);
  if (audit.remoteChecked === false) {
    warn(
      "the remote could not be read, so refs/pull/* were not audited",
      "Run `npm run oss:prune-refs` with network access before publishing; an empty list here means 'not checked', not 'clean'."
    );
    return;
  }
  const personal = audit.pullRequestPersonalAuthors || [];
  if (personal.length > 0) {
    warn(
      `${personal.length} pull-request ref(s) carry a non-noreply author: ${personal
        .map((entry) => `${entry.pr} (${entry.emails.join(", ")})`)
        .join(", ")}`,
      "Harmless for outside contributors (their address is public on GitHub anyway); it only matters for this project's own refs, where a rewrite is the fix."
    );
  }
  const leaking = audit.pullRequests || [];
  if (leaking.length > 0) {
    fail(
      `${leaking.length} pull-request ref(s) still reach old history: ${leaking
        .map((pr) => `${pr.ref} (${pr.reasons.join("; ")})`)
        .join(", ")}`,
      "refs/pull/* are server-managed and survive both branch deletion and a force-push. Publish from a freshly created repository (or ask GitHub Support to purge), then re-run this check against the new remote."
    );
  }
}

if (!process.argv.includes("--no-remote") && safeGit(["remote", "get-url", "origin"]).trim()) {
  try {
    const raw = execFileSync(
      process.execPath,
      [path.join(siteRoot, "scripts", "prune-stale-refs.js"), "--json"],
      { cwd: siteRoot, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }
    );
    consumeRemoteAudit(raw);
  } catch (error) {
    if (error.stdout) {
      try {
        consumeRemoteAudit(error.stdout);
      } catch {
        warn(
          "could not audit remote pull-request refs",
          "Run `npm run oss:prune-refs` manually; it fails if refs/pull/* still reach old history."
        );
      }
    } else {
      warn(
        "could not audit remote pull-request refs (no network?)",
        "Run `npm run oss:prune-refs` manually before publishing; pass --no-remote to skip this check."
      );
    }
  }
} else {
  notes.push("remote ref audit skipped (--no-remote); refs/pull/* were not checked.");
}

// ---------------------------------------------------------------------------
// 6. Branch-protection ruleset must name a check that actually exists.
// ---------------------------------------------------------------------------
// A ruleset whose required-status context does not byte-match the workflow job
// name blocks every merge, and a mis-encoded file (CP1252 middot instead of
// UTF-8) is invisible when you read it in an editor.
try {
  const ruleset = fs.readFileSync(path.join(repoRoot, ".github", "ruleset.json"), "utf8");
  const ci = fs.readFileSync(path.join(repoRoot, ".github", "workflows", "ci.yml"), "utf8");
  const wanted = (ruleset.match(/"context":\s*"([^"]+)"/) || [])[1];
  const jobName = (ci.match(/^\s{4}name:\s*(.+)$/m) || [])[1];
  if (wanted && jobName && wanted.trim() !== jobName.trim()) {
    fail(
      `ruleset.json requires status check "${wanted}" but ci.yml reports "${jobName}"`,
      "Make the two strings byte-identical and save ruleset.json as UTF-8; otherwise branch protection blocks every merge."
    );
  }
} catch {
  // Missing ruleset/ci files are outside this check's scope.
}

// ---------------------------------------------------------------------------
// 7. The tree-level secret scan (same one the release gate runs).
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
