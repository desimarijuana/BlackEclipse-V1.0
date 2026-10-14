// ─── Code capability BROWSER client ──────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/code/**`), which proxy to the
// Python runtime. This module MUST stay client-safe: no `child_process`, no `fs`,
// no `ensurePythonRuntime` (that lives in the server-only `code-client.ts`). Fetch
// only. Without this split the Phase-5 screens cannot be mounted from a client
// component — importing the server client pulls `child_process` into the browser
// bundle and the page fails to compile.

import type { Autonomy, CodeApproval, CodePlan, CodeTask, CodeTaskDiff, TaskStatus, CreateTaskInput, PromotionFile, PromotionPreview } from './code-client';

// Re-export the wire types so a component imports everything from ONE client-safe
// module (a type-only re-export is erased at compile time — no server code ships).
export type { Autonomy, CodeApproval, CodePlan, CodeTask, CodeTaskDiff, TaskStatus, CreateTaskInput, PromotionFile, PromotionPreview };

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

// ── Promotion: put a reviewed change into the real project (Phase 15) ───────
// The client-safe path: the two Next.js routes proxy to the runtime, which owns
// the preview and the single-use decision. This module only carries it.

/** Preview exactly what a task's change would put into the real project. */
export async function previewPromotion(
  taskId: string,
): Promise<{ preview: PromotionPreview; approval: { id: string; status: string } | null }> {
  return api(`/api/code/tasks/${encodeURIComponent(taskId)}/promote/preview`, { method: 'POST' });
}

/** Confirm a previewed change and put it into the real project. */
export async function applyPromotion(
  taskId: string,
  approvalId: string,
  previewDigest: string,
): Promise<{ ok: boolean; filesChanged: number }> {
  const body = await api<{ promotion: { ok: boolean; filesChanged: number } }>(
    `/api/code/tasks/${encodeURIComponent(taskId)}/promote`,
    { method: 'POST', body: JSON.stringify({ approvalId, previewDigest }) },
  );
  return body.promotion;
}

// ── Workspace folders + editor (client-safe) ─────────────────────────────────

import type { BrowseEntry, BrowseResult, EditorEntry, EditorFileResult, EditorTreeResult, TrustedRoot } from './code-client';
export type { BrowseEntry, BrowseResult, EditorEntry, EditorFileResult, EditorTreeResult, TrustedRoot };

export async function browseFolders(path?: string): Promise<BrowseResult> {
  const q = path ? `?path=${encodeURIComponent(path)}` : '';
  return api<BrowseResult>(`/api/workspace/browse${q}`);
}

export async function listTrustedRoots(): Promise<TrustedRoot[]> {
  const body = await api<{ roots: TrustedRoot[] }>('/api/workspace/roots');
  return body.roots ?? [];
}

export async function approveTrustedRoot(path: string, label?: string): Promise<TrustedRoot> {
  const body = await api<{ root: TrustedRoot }>('/api/workspace/roots', {
    method: 'POST',
    body: JSON.stringify({ path, label }),
  });
  return body.root;
}

export async function selectTrustedRoot(rootId: string | null): Promise<TrustedRoot | null> {
  const body = await api<{ selected: TrustedRoot | null }>('/api/workspace/roots/select', {
    method: 'POST',
    body: JSON.stringify({ rootId }),
  });
  return body.selected;
}

export async function revokeTrustedRoot(rootId: string): Promise<void> {
  await api(`/api/workspace/roots/${encodeURIComponent(rootId)}`, { method: 'DELETE' });
}

export async function listWorkspaceFiles(path = '.'): Promise<EditorTreeResult> {
  return api<EditorTreeResult>(`/api/workspace/files?path=${encodeURIComponent(path)}`);
}

export async function readWorkspaceFile(path: string): Promise<EditorFileResult> {
  return api<EditorFileResult>('/api/workspace/file/read', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export async function writeWorkspaceFile(path: string, content: string): Promise<{ path: string; bytes: number }> {
  return api<{ path: string; bytes: number }>('/api/workspace/file/write', {
    method: 'POST',
    body: JSON.stringify({ path, content }),
  });
}

export async function makeWorkspaceFolder(path: string): Promise<{ path: string }> {
  return api<{ path: string }>('/api/workspace/file/mkdir', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export async function deleteWorkspacePath(path: string): Promise<{ path: string; removed: boolean }> {
  return api<{ path: string; removed: boolean }>('/api/workspace/file/delete', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

// ── Pure, client-safe render helpers (mirrors of the server client) ─────────

export type CheckClaimKind =
  | 'tests_pass'
  | 'typecheck_clean'
  | 'build_ok'
  | 'lint_clean'
  | 'artifacts_verified'
  | 'change_reviewed';

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
  /** Phase 19: artifact observations (one per check). Additive, old-row-safe. */
  artifacts: CodeArtifactRecord[];
  /** Phase 19: recorded change reviews. Additive, old-row-safe. */
  reviews: CodeReviewRecord[];
}

export interface CodeArtifactRecord {
  artifactName: string;
  kind: string;
  check: string;
  passed: boolean;
  detail: string;
}

export interface CodeReviewFinding {
  rule: string;
  summary: string;
  severity: 'blocking' | 'advisory';
  path: string;
  line: number | null;
}

export interface CodeReviewRecord {
  filesReviewed: number;
  findings: CodeReviewFinding[];
  unevaluated: string[];
}

export function claimStatusKey(supported: boolean): 'code.proof.verified' | 'code.proof.notChecked' {
  return supported ? 'code.proof.verified' : 'code.proof.notChecked';
}

function _artifactRecords(raw: unknown): CodeArtifactRecord[] {
  if (!Array.isArray(raw)) return [];
  return (raw as unknown[])
    .filter((a): a is Record<string, unknown> => a !== null && typeof a === 'object')
    .map((a) => ({
      artifactName: String(a.artifactName ?? ''),
      kind: String(a.kind ?? ''),
      check: String(a.check ?? ''),
      passed: Boolean(a.passed),
      detail: String(a.detail ?? ''),
    }))
    .filter((a) => a.artifactName && a.check)
    .slice(0, 200);
}

function _reviewRecords(raw: unknown): CodeReviewRecord[] {
  if (!Array.isArray(raw)) return [];
  return (raw as unknown[])
    .filter(
      (r): r is Record<string, unknown> =>
        r !== null && typeof r === 'object' && (r as Record<string, unknown>).ran === true,
    )
    .map((r) => ({
      filesReviewed: Number(r.filesReviewed ?? 0),
      findings: Array.isArray(r.findings)
        ? (r.findings as unknown[])
            .filter((f): f is Record<string, unknown> => f !== null && typeof f === 'object')
            .map((f) => ({
              rule: String(f.rule ?? ''),
              summary: String(f.summary ?? ''),
              severity: f.severity === 'blocking' ? ('blocking' as const) : ('advisory' as const),
              path: String(f.path ?? ''),
              line: typeof f.line === 'number' ? f.line : null,
            }))
            .slice(0, 50)
        : [],
      unevaluated: Array.isArray(r.unevaluated)
        ? (r.unevaluated as unknown[]).map(String).slice(0, 10)
        : [],
    }))
    .slice(0, 8);
}

export function coerceCodeVerification(raw: unknown): CodeVerification | null {
  if (raw === null || typeof raw !== 'object') return null;
  const blob = raw as Record<string, unknown>;
  const records = Array.isArray(blob.records) ? (blob.records as CodeVerificationRecord[]) : [];
  const claims = Array.isArray(blob.claims) ? (blob.claims as CodeVerificationClaim[]) : [];
  const artifacts = _artifactRecords(blob.artifacts);
  const reviews = _reviewRecords(blob.reviews);
  if (
    records.length === 0 &&
    claims.length === 0 &&
    artifacts.length === 0 &&
    reviews.length === 0 &&
    !blob.repair
  ) {
    return null;
  }
  return {
    runId: String(blob.runId ?? ''),
    records,
    claims,
    unverifiedCount: Number(blob.unverifiedCount ?? 0),
    repair: (blob.repair as CodeVerificationRepair | null) ?? null,
    truncated: Boolean(blob.truncated),
    artifacts,
    reviews,
  };
}
