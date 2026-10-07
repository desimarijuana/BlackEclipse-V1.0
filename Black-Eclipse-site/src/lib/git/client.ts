// Client helpers for the in-app git workflow. Thin wrappers over /api/git —
// request shaping and honest errors only.
//
// The Git ENGINE is the Python runtime (`python/harness/git/`); `/api/git` proxies
// to it. This module adds NO git logic. Types come from the client-safe
// `types.ts` so this bundle never imports a server-only module.

import type { GitCommitInfo, GitStatus } from "./types";

export type { GitCommitInfo, GitFileChange, GitStatus } from "./types";

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = body as { error?: string; code?: string };
    throw new Error(err.error || `Git request failed (${res.status})`);
  }
  return body as T;
}

export async function fetchGitStatus(): Promise<GitStatus> {
  const res = await fetch("/api/git?action=status", { cache: "no-store" });
  const body = await json<{ status: GitStatus }>(res);
  return body.status;
}

export async function fetchGitDiff(staged = false): Promise<string> {
  const res = await fetch(`/api/git?action=diff${staged ? "&staged=1" : ""}`, { cache: "no-store" });
  const body = await json<{ diff: string }>(res);
  return body.diff;
}

export async function fetchGitLog(): Promise<GitCommitInfo[]> {
  const res = await fetch("/api/git?action=log", { cache: "no-store" });
  const body = await json<{ commits: GitCommitInfo[] }>(res);
  return body.commits;
}

export async function draftCommitMessage(): Promise<string> {
  const res = await fetch("/api/git?action=draft", { cache: "no-store" });
  const body = await json<{ message: string }>(res);
  return body.message;
}

async function post<T>(payload: Record<string, unknown>): Promise<T> {
  const res = await fetch("/api/git", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return json<T>(res);
}

export async function stagePaths(paths: string[]): Promise<GitStatus> {
  const body = await post<{ status: GitStatus }>({ action: "stage", paths });
  return body.status;
}

export async function unstagePaths(paths: string[]): Promise<GitStatus> {
  const body = await post<{ status: GitStatus }>({ action: "unstage", paths });
  return body.status;
}

export async function commitChanges(message: string): Promise<{ hash: string; subject: string; status: GitStatus }> {
  const body = await post<{ commit: { hash: string; subject: string }; status: GitStatus }>({ action: "commit", message });
  return { ...body.commit, status: body.status };
}

export async function pushChanges(setUpstream = false): Promise<{ branch: string; output: string; status: GitStatus }> {
  const body = await post<{ push: { branch: string; output: string }; status: GitStatus }>({ action: "push", setUpstream });
  return { ...body.push, status: body.status };
}
