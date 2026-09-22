// ── Git workflow service (server-only) ───────────────────────────────────────
// A small, safe wrapper over the repo's git CLI for the in-app "plan → review →
// commit → push" surface. Everything runs through `execFile` with an argument
// array — never a shell string — so a commit message or path cannot inject a
// command.
//
// Safety rails, in code rather than convention:
//   * refuses to commit when staged changes look like secrets (.env, keys, DBs)
//   * never force-pushes, never rewrites history, never touches config
//   * `push` is a separate, explicit action from `commit`
//   * the repo root is resolved once, and every command runs inside it

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";

const run = promisify(execFile);

export interface GitFileChange {
  path: string;
  index: string; // staged status code (e.g. "M", "A", "?")
  worktree: string; // unstaged status code
  staged: boolean;
}

export interface GitStatus {
  available: boolean;
  branch: string | null;
  upstream: string | null;
  ahead: number;
  behind: number;
  files: GitFileChange[];
  stagedCount: number;
  unstagedCount: number;
  untrackedCount: number;
  clean: boolean;
  /** Human-readable reason when `available` is false. */
  reason?: string;
}

export interface GitCommitInfo {
  hash: string;
  shortHash: string;
  subject: string;
  author: string;
  date: string;
}

/** Patterns that must never be committed. Checked against staged paths. */
const SECRET_PATTERNS = [
  /(^|\/)\.env(\.|$)/i,
  /\.(pem|key|p12|pfx|keystore)$/i,
  /(^|\/)id_(rsa|ed25519|ecdsa)$/i,
  /\.db(-shm|-wal)?$/i,
  /(^|\/)credentials(\.json)?$/i,
  /(^|\/)\.connector-key$/i,
  /(^|\/)secrets?\.(json|ya?ml|toml)$/i,
];

export class GitError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = "GitError";
    this.code = code;
  }
}

/**
 * The repository root, resolved once. `git` reports paths (in `status`,
 * `diff`, etc.) relative to the repo root, so every command must run there —
 * otherwise `git add <path>` from a subdirectory resolves the pathspec against
 * the wrong base. `BLACK_ECLIPSE_GIT_ROOT` overrides for non-standard layouts.
 */
let cachedRoot: string | null = null;
async function repoRoot(): Promise<string> {
  if (cachedRoot) return cachedRoot;
  const override = process.env.BLACK_ECLIPSE_GIT_ROOT;
  if (override) {
    cachedRoot = override;
    return cachedRoot;
  }
  try {
    const { stdout } = await run("git", ["rev-parse", "--show-toplevel"], {
      cwd: process.cwd(),
      windowsHide: true,
    });
    cachedRoot = stdout.trim() || process.cwd();
  } catch {
    cachedRoot = process.cwd();
  }
  return cachedRoot;
}

async function git(args: string[], opts: { maxBuffer?: number } = {}): Promise<string> {
  const cwd = await repoRoot();
  try {
    const { stdout } = await run("git", args, {
      cwd,
      maxBuffer: opts.maxBuffer ?? 4 * 1024 * 1024,
      windowsHide: true,
    });
    return stdout;
  } catch (err) {
    const e = err as { stderr?: string; message?: string; code?: string };
    if (e.code === "ENOENT") {
      throw new GitError("GIT_UNAVAILABLE", "git is not installed or not on PATH");
    }
    throw new GitError("GIT_COMMAND_FAILED", (e.stderr || e.message || "git command failed").trim());
  }
}

/** True when the working directory is inside a git repository. */
export async function isGitRepo(): Promise<boolean> {
  try {
    const out = await git(["rev-parse", "--is-inside-work-tree"]);
    return out.trim() === "true";
  } catch {
    return false;
  }
}

function parseStatusLine(line: string): GitFileChange | null {
  // Porcelain v1: "XY <path>" (with rename "XY <old> -> <new>").
  if (line.length < 4) return null;
  const index = line[0];
  const worktree = line[1];
  let filePath = line.slice(3);
  const arrow = filePath.indexOf(" -> ");
  if (arrow !== -1) filePath = filePath.slice(arrow + 4);
  return {
    path: filePath,
    index,
    worktree,
    staged: index !== " " && index !== "?" && index !== "!",
  };
}

export async function getStatus(): Promise<GitStatus> {
  if (!(await isGitRepo())) {
    return {
      available: false,
      branch: null, upstream: null, ahead: 0, behind: 0,
      files: [], stagedCount: 0, unstagedCount: 0, untrackedCount: 0, clean: true,
      reason: "Not a git repository",
    };
  }

  let branch: string | null = null;
  try {
    branch = (await git(["rev-parse", "--abbrev-ref", "HEAD"])).trim() || null;
  } catch {
    branch = null;
  }

  let upstream: string | null = null;
  let ahead = 0;
  let behind = 0;
  try {
    upstream = (await git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])).trim();
    const counts = (await git(["rev-list", "--left-right", "--count", "@{u}...HEAD"])).trim().split(/\s+/);
    behind = Number(counts[0]) || 0;
    ahead = Number(counts[1]) || 0;
  } catch {
    // No upstream configured — that's fine, not an error.
  }

  const out = await git(["status", "--porcelain"]);
  const files = out
    .split("\n")
    .map((l) => l.replace(/\r$/, ""))
    .filter(Boolean)
    .map(parseStatusLine)
    .filter((f): f is GitFileChange => f !== null);

  const stagedCount = files.filter((f) => f.staged).length;
  const untrackedCount = files.filter((f) => f.index === "?").length;
  const unstagedCount = files.length - stagedCount - untrackedCount;

  return {
    available: true,
    branch,
    upstream,
    ahead,
    behind,
    files,
    stagedCount,
    unstagedCount,
    untrackedCount,
    clean: files.length === 0,
  };
}

/** Names of staged paths that match a secret pattern (blocks a commit). */
export function findSecretPaths(paths: string[]): string[] {
  return paths.filter((p) => SECRET_PATTERNS.some((re) => re.test(p)));
}

export async function getStagedPaths(): Promise<string[]> {
  const out = await git(["diff", "--cached", "--name-only"]);
  return out.split("\n").map((l) => l.replace(/\r$/, "")).filter(Boolean);
}

/** A unified diff. `staged` selects the index diff instead of the worktree. */
export async function getDiff(staged = false): Promise<string> {
  const args = staged ? ["diff", "--cached"] : ["diff"];
  const out = await git([...args, "--no-color"], { maxBuffer: 8 * 1024 * 1024 });
  return out;
}

export async function getLog(limit = 15): Promise<GitCommitInfo[]> {
  const format = "%H%x1f%h%x1f%s%x1f%an%x1f%aI";
  const out = await git(["log", `-n${Math.min(Math.max(limit, 1), 100)}`, `--pretty=format:${format}`]);
  return out
    .split("\n")
    .map((l) => l.replace(/\r$/, ""))
    .filter(Boolean)
    .map((line) => {
      const [hash, shortHash, subject, author, date] = line.split("\x1f");
      return { hash, shortHash, subject, author, date };
    });
}

/** Stage specific paths (or all changes when `paths` is empty). */
export async function stage(paths: string[]): Promise<void> {
  if (paths.length === 0) throw new GitError("NOTHING_TO_STAGE", "No paths to stage");
  // Guard each path against option-injection: git treats a leading "-" as a flag.
  for (const p of paths) {
    if (p.startsWith("-")) throw new GitError("INVALID_PATH", `Invalid path: ${p}`);
  }
  await git(["add", "--", ...paths]);
}

export async function unstage(paths: string[]): Promise<void> {
  if (paths.length === 0) return;
  await git(["reset", "--", ...paths]);
}

/**
 * Commit the staged index. Refuses when nothing is staged or a staged path
 * looks like a secret. Returns the new commit's short hash + subject.
 */
export async function commit(message: string): Promise<{ hash: string; subject: string }> {
  const trimmed = message.trim();
  if (!trimmed) throw new GitError("EMPTY_MESSAGE", "A commit message is required");

  const staged = await getStagedPaths();
  if (staged.length === 0) throw new GitError("NOTHING_STAGED", "No staged changes to commit");

  const secrets = findSecretPaths(staged);
  if (secrets.length > 0) {
    throw new GitError(
      "SECRET_BLOCKED",
      `Refusing to commit paths that may contain secrets: ${secrets.join(", ")}`
    );
  }

  await git(["commit", "-m", trimmed]);
  const head = (await git(["rev-parse", "HEAD"])).trim();
  const subject = (await git(["log", "-1", "--pretty=%s"])).trim();
  return { hash: head, subject };
}

/**
 * Push the current branch to its upstream. Never force. When the branch has no
 * upstream, `setUpstream` sets it on the first push.
 */
export async function push(setUpstream = false): Promise<{ branch: string; output: string }> {
  const branch = (await git(["rev-parse", "--abbrev-ref", "HEAD"])).trim();
  const args = setUpstream ? ["push", "--set-upstream", "origin", branch] : ["push"];
  const output = await git(args, { maxBuffer: 4 * 1024 * 1024 });
  return { branch, output: output.trim() };
}

/**
 * Draft a commit message from the staged changes — a *suggestion*, not an
 * invention: it is built from the actual file paths and change types.
 */
export async function draftCommitMessage(): Promise<string> {
  const staged = await getStagedPaths();
  if (staged.length === 0) return "";
  const stat = await git(["diff", "--cached", "--name-status"]);
  const groups: Record<string, string[]> = { A: [], M: [], D: [], R: [] };
  for (const line of stat.split("\n").filter(Boolean)) {
    const [code, ...rest] = line.replace(/\r$/, "").split("\t");
    const key = code[0];
    const paths = groups[key] ?? (groups[key] = []);
    paths.push(rest[rest.length - 1]);
  }
  const verb =
    groups.A.length && !groups.M.length && !groups.D.length
      ? "Add"
      : groups.D.length && !groups.A.length && !groups.M.length
      ? "Remove"
      : "Update";
  const area = commonArea(staged);
  const count = staged.length;
  return `${verb} ${area}${count === 1 ? "" : ` (${count} files)`}`;
}

/** The deepest path prefix shared by every staged file, for a message subject. */
function commonArea(paths: string[]): string {
  if (paths.length === 0) return "changes";
  const split = paths.map((p) => p.split("/"));
  const first = split[0];
  let prefix = first;
  for (const parts of split.slice(1)) {
    let i = 0;
    while (i < prefix.length && i < parts.length - 1 && prefix[i] === parts[i]) i++;
    prefix = prefix.slice(0, i);
  }
  const area = prefix.join("/") || path.basename(paths[0]);
  return area;
}
