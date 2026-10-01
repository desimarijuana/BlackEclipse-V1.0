// ─── Code capability BROWSER client ──────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/code/**`), which proxy to the
// Python runtime. This module MUST stay client-safe: no `child_process`, no `fs`,
// no `ensurePythonRuntime` (that lives in the server-only `code-client.ts`). Fetch
// only. Without this split the Phase-5 screens cannot be mounted from a client
// component — importing the server client pulls `child_process` into the browser
// bundle and the page fails to compile.

import type { Autonomy, CodeApproval, CodePlan, CodeTask, CodeTaskDiff, TaskStatus, CreateTaskInput } from './code-client';

// Re-export the wire types so a component imports everything from ONE client-safe
// module (a type-only re-export is erased at compile time — no server code ships).
export type { Autonomy, CodeApproval, CodePlan, CodeTask, CodeTaskDiff, TaskStatus, CreateTaskInput };

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

export async function listCodeTasks(): Promise<CodeTask[]> {
  const body = await api<{ tasks: CodeTask[] }>('/api/code/tasks');
  return body.tasks ?? [];
}

export async function getCodeTask(id: string): Promise<CodeTask> {
  const body = await api<{ task: CodeTask }>(`/api/code/tasks/${encodeURIComponent(id)}`);
  return body.task;
}

export async function createCodeTask(input: CreateTaskInput): Promise<CodeTask> {
  const body = await api<{ task: CodeTask }>('/api/code/tasks', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return body.task;
}

export async function cancelCodeTask(id: string): Promise<{ cancelled: boolean; worktreeReleased: boolean }> {
  return api(`/api/code/tasks/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
}

export async function discardCodeTask(id: string): Promise<{ discarded: boolean }> {
  return api(`/api/code/tasks/${encodeURIComponent(id)}/discard`, { method: 'POST' });
}

export async function resumeCodeTask(id: string): Promise<unknown> {
  return api(`/api/code/tasks/${encodeURIComponent(id)}/resume`, { method: 'POST' });
}

export async function acceptCodePlan(id: string, steps: CodePlan['steps'], checkClasses: string[]): Promise<unknown> {
  return api(`/api/code/tasks/${encodeURIComponent(id)}/plan`, {
    method: 'POST',
    body: JSON.stringify({ steps, checkClasses }),
  });
}

export async function listCodeApprovals(): Promise<CodeApproval[]> {
  const body = await api<{ approvals: CodeApproval[] }>('/api/code/approvals');
  return body.approvals ?? [];
}

export async function decideCodeApproval(id: string, approve: boolean, reason = ''): Promise<unknown> {
  return api(`/api/code/approvals/${encodeURIComponent(id)}`, {
    method: 'POST',
    body: JSON.stringify({ approve, reason }),
  });
}

/** The change a task made, in everyday words plus the raw text behind "details". */
export async function getCodeTaskDiff(id: string): Promise<CodeTaskDiff | null> {
  try {
    const body = await api<{ diff: CodeTaskDiff }>(`/api/code/tasks/${encodeURIComponent(id)}/diff`);
    return body.diff ?? null;
  } catch {
    // A task with no bound work area has no diff; that is not an error.
    return null;
  }
}

// ── Pure, client-safe render helpers (mirrors of the server client) ─────────
// These hold no state and no secrets; they are the ONE place each status word is
// chosen, so "verified" and an unsupported claim can never coincide.

export type CheckClaimKind = 'tests_pass' | 'typecheck_clean' | 'build_ok' | 'lint_clean';

export interface CodeVerificationRecord {
  commandExecutionId: string;
  commandClass: string;
  exitCode: number;
  durationMs: number;
  outputDigest: string;
  argv: string[];
  startedAt: string;
  workspaceId: string | null;
}

export interface CodeVerificationClaim {
  sentence: string;
  kind: CheckClaimKind;
  matchedClasses: string[];
  supported: boolean;
  evidenceExecutionId: string | null;
  evidenceDigest: string | null;
  evidenceExitCode?: number | null;
}

export interface CodeVerificationRepair {
  status: 'passed' | 'unrepairable' | 'budget_exhausted' | 'refused' | 'no_checks';
  repairAttempts: number;
  maxAttempts: number;
  failedClass: string | null;
  failedOutputDigest: string | null;
  stoppedReason: string | null;
}

export interface CodeVerification {
  runId: string;
  records: CodeVerificationRecord[];
  claims: CodeVerificationClaim[];
  unverifiedCount: number;
  repair: CodeVerificationRepair | null;
  truncated: boolean;
}

export function claimStatusKey(supported: boolean): 'code.proof.verified' | 'code.proof.notChecked' {
  return supported ? 'code.proof.verified' : 'code.proof.notChecked';
}

export function coerceCodeVerification(raw: unknown): CodeVerification | null {
  if (raw === null || typeof raw !== 'object') return null;
  const blob = raw as Record<string, unknown>;
  const records = Array.isArray(blob.records) ? (blob.records as CodeVerificationRecord[]) : [];
  const claims = Array.isArray(blob.claims) ? (blob.claims as CodeVerificationClaim[]) : [];
  if (records.length === 0 && claims.length === 0 && !blob.repair) return null;
  return {
    runId: String(blob.runId ?? ''),
    records,
    claims,
    unverifiedCount: Number(blob.unverifiedCount ?? 0),
    repair: (blob.repair as CodeVerificationRepair | null) ?? null,
    truncated: Boolean(blob.truncated),
  };
}
