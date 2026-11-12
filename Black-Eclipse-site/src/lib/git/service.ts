// ── Git front door (server-only) ──────────────────────────────────────────────
//
// A THIN proxy over the Python runtime's `/git/*` routes. The Git ENGINE lives in
// `python/harness/git/` — discovery, the closed operation table, the executor, the
// safety/risk engine, the operation journal, the lock and the recovery manager.
// This module adds NO Git logic of its own: it forwards to the runtime, where the
// repository is resolved server-side, mutations are journaled and locked, and a
// dangerous/remote action is gated by the same authorizer the agent uses.
//
// This replaces the earlier standalone TypeScript git wrapper. Per the
// architecture, the UI must consume the SAME service the agent uses — never a
// second implementation.

import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { HarnessRuntimeUnavailable } from "@/lib/harness/clients/python-client";
import type { GitCommitInfo, GitFileChange, GitStatus } from "./types";

// Re-export the wire types so `service.ts` stays the server-side entry point.
export type { GitCommitInfo, GitFileChange, GitStatus } from "./types";

export class GitError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = "GitError";
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const { timeoutMs = 120_000, ...rest } = init;
  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(rest.headers ?? {}),
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new GitError(String((body as { code?: string }).code || "GIT_FAILED"), detail);
  }
  return body as T;
}

// ── Read: status ───────────────────────────────────────────────────────────────

interface RuntimeStatus {
  available?: boolean;
  branch?: string | null;
  upstream?: string | null;
  ahead?: number;
  behind?: number;
  staged?: Array<{ path: string; status: string }>;
  unstaged?: Array<{ path: string; status: string }>;
  untracked?: string[];
  clean?: boolean;
  summary?: { staged?: number; unstaged?: number; untracked?: number; conflicts?: number };
  error?: { code?: string; message?: string };
}

export async function isGitRepo(): Promise<boolean> {
  try {
    const body = await request<{ is_repository?: boolean }>("/git/info", { method: "GET" });
    return body.is_repository === true;
  } catch {
    return false;
  }
}

/** The staged/unstaged/untracked state, mapped to the panel's shape. */
export async function getStatus(): Promise<GitStatus> {
  let info: { is_repository?: boolean; branch?: string | null; reason?: string };
  try {
    info = await request("/git/info", { method: "GET" });
  } catch (err) {
    if (err instanceof HarnessRuntimeUnavailable) throw err;
    return emptyStatus(err instanceof Error ? err.message : "Git is not available here.");
  }
  if (!info.is_repository) {
    return emptyStatus("This folder is not set up to track versions yet.");
  }
  const body = await request<{ status: RuntimeStatus }>("/git/status", { method: "GET" });
  const s = body.status ?? {};
  const staged = s.staged ?? [];
  const unstaged = s.unstaged ?? [];
  const untracked = s.untracked ?? [];
  const files: GitFileChange[] = [
    ...staged.map((f) => ({ path: f.path, index: statusLetter(f.status), worktree: " ", staged: true })),
    ...unstaged.map((f) => ({ path: f.path, index: " ", worktree: statusLetter(f.status), staged: false })),
    ...untracked.map((p) => ({ path: p, index: "?", worktree: "?", staged: false })),
  ];
  return {
    available: true,
    branch: s.branch ?? null,
    upstream: s.upstream ?? null,
    ahead: s.ahead ?? 0,
    behind: s.behind ?? 0,
    files,
    stagedCount: s.summary?.staged ?? staged.length,
    unstagedCount: s.summary?.unstaged ?? unstaged.length,
    untrackedCount: s.summary?.untracked ?? untracked.length,
    clean: s.clean ?? files.length === 0,
  };
}

function emptyStatus(reason: string): GitStatus {
  return {
    available: false, branch: null, upstream: null, ahead: 0, behind: 0,
    files: [], stagedCount: 0, unstagedCount: 0, untrackedCount: 0, clean: true, reason,
  };
}

function statusLetter(state: string): string {
  return {
    added: "A", modified: "M", deleted: "D", renamed: "R", copied: "C",
    untracked: "?", conflicted: "U", typechanged: "T",
  }[state] ?? "M";
}

// ── Read: diff / log / draft ─────────────────────────────────────────────────────

export async function getDiff(staged = false): Promise<string> {
  const path = staged ? "/git/diff?cached=1" : "/git/diff";
  const body = await request<{ diff?: { patch?: string } }>(path, { method: "GET" });
  return body.diff?.patch ?? "";
}

export async function getLog(limit = 15): Promise<GitCommitInfo[]> {
  const body = await request<{ commits?: Array<{ sha: string; short_sha: string; subject: string; author: string; date: string }> }>(
    `/git/log?maxCount=${Math.min(Math.max(limit, 1), 100)}`,
    { method: "GET" },
  );
  return (body.commits ?? []).map((c) => ({
    hash: c.sha, shortHash: c.short_sha, subject: c.subject, author: c.author, date: c.date,
  }));
}

export async function draftCommitMessage(): Promise<string> {
  const body = await request<{ draft?: { message?: string } }>("/git/draft-message", { method: "GET" });
  return body.draft?.message ?? "";
}

// ── Mutations (journaled + locked + risk-gated in the runtime) ──────────────────

interface Outcome {
  success?: boolean;
  error?: { code?: string; message?: string };
  result?: Record<string, unknown>;
}

async function mutation(path: string, payload: Record<string, unknown>): Promise<Outcome> {
  const body = await request<{ success?: boolean; outcome?: Outcome }>(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const outcome = body.outcome ?? {};
  if (body.success === false || outcome.success === false) {
    const err = outcome.error ?? {};
    throw new GitError(err.code || "GIT_FAILED", err.message || "The version operation did not complete.");
  }
  return outcome;
}

export async function stage(paths: string[]): Promise<void> {
  if (paths.length === 0) throw new GitError("NOTHING_TO_STAGE", "No paths to stage.");
  await mutation("/git/stage", { paths });
}

export async function unstage(paths: string[]): Promise<void> {
  if (paths.length === 0) return;
  await mutation("/git/unstage", { paths });
}

export async function commit(message: string): Promise<{ hash: string; subject: string }> {
  const trimmed = message.trim();
  if (!trimmed) throw new GitError("EMPTY_MESSAGE", "A commit message is required");
  const outcome = await mutation("/git/commit", { message: trimmed });
  const result = (outcome.result ?? {}) as { commit?: string; summary?: string };
  return { hash: String(result.commit ?? ""), subject: String(result.summary ?? "").trim() };
}

export async function push(setUpstream = false): Promise<{ branch: string; output: string }> {
  const outcome = await mutation("/git/push", { setUpstream });
  const result = (outcome.result ?? {}) as { branch?: string; output?: string };
  return { branch: String(result.branch ?? ""), output: String(result.output ?? "") };
}
