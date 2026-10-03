// ─── Code capability front door (Phases 4–5) ────────────────────────────────
// Thin, typed proxy over the Python runtime's /code routes plus the read-only
// `codeVerification` blob types. This module adds NO agentic logic (mirrors
// python-client.ts): it validates, forwards, and returns what the runtime owns.
// Operator-gated routes present the runtime secret by transport/token, never a
// body boolean.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type Autonomy = "plan_only" | "edit_verify" | "approve_external";
export type TaskStatus =
  | "created" | "plan_review" | "completed" | "failed" | "cancelled" | "discarded";

export interface CodePlan {
  planDigest: string;
  steps: Array<{ id: string; description: string; files: string[] }>;
  files: string[];
  checkClasses: string[];
}

export interface CodeTask {
  id: string;
  status: TaskStatus;
  autonomy: Autonomy;
  workspaceId: string | null;
  query: string;
  plan: CodePlan | null;
  verification: CodeVerification | null;
  repair: CodeVerificationRepair | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface CodeApproval {
  id: string;
  kind: string;
  workspaceId: string | null;
  serverId: string;
  effect: string;
  status: string;
  actionSummary: string | null;
  createdAt: string;
}

export interface CreateTaskInput {
  query: string;
  autonomy: Autonomy;
  workspaceId?: string;
  modelSettings: Record<string, unknown>;
  callbackBaseUrl?: string;
  callbackToken?: string;
  /** Edit the selected real folder directly instead of a disposable copy. */
  direct?: boolean;
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
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

export async function listCodeTasks(): Promise<CodeTask[]> {
  const body = await request<{ tasks: CodeTask[] }>("/code/tasks", { method: "GET" });
  return body.tasks ?? [];
}

export async function getCodeTask(id: string): Promise<CodeTask> {
  const body = await request<{ task: CodeTask }>(`/code/tasks/${encodeURIComponent(id)}`, { method: "GET" });
  return body.task;
}

export async function createCodeTask(input: CreateTaskInput): Promise<CodeTask> {
  const body = await request<{ task: CodeTask }>("/code/tasks", {
    method: "POST",
    body: JSON.stringify(input),
    timeoutMs: 600_000,
  });
  return body.task;
}

export async function cancelCodeTask(id: string): Promise<{ cancelled: boolean; worktreeReleased: boolean }> {
  return request(`/code/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}

export async function discardCodeTask(id: string): Promise<{ discarded: boolean }> {
  return request(`/code/tasks/${encodeURIComponent(id)}/discard`, { method: "POST" });
}

export async function acceptCodePlan(id: string, steps: CodePlan["steps"], checkClasses: string[]): Promise<unknown> {
  return request(`/code/tasks/${encodeURIComponent(id)}/plan/accept`, {
    method: "POST",
    body: JSON.stringify({ steps, checkClasses }),
  });
}

export interface CodeTaskDiff {
  available: boolean;
  unified: string;
  digest: string;
  filesChanged: number;
  added: string[];
  modified: string[];
  deleted: string[];
}

/** The change a task made, in everyday words plus the raw text behind "details". */
export async function getCodeTaskDiff(id: string): Promise<CodeTaskDiff | null> {
  try {
    const body = await request<{ diff: CodeTaskDiff }>(
      `/code/tasks/${encodeURIComponent(id)}/diff`,
      { method: "GET", timeoutMs: 30_000 },
    );
    return body.diff ?? null;
  } catch {
    // A task with no bound work area has no diff; that is not an error.
    return null;
  }
}

export async function resumeCodeTask(id: string): Promise<unknown> {
  return request(`/code/tasks/${encodeURIComponent(id)}/resume`, { method: "POST" });
}

export async function listCodeApprovals(): Promise<CodeApproval[]> {
  const body = await request<{ approvals: CodeApproval[] }>("/code/approvals", { method: "GET" });
  return body.approvals ?? [];
}

export async function decideCodeApproval(id: string, approve: boolean, reason = ""): Promise<unknown> {
  return request(`/code/approvals/${encodeURIComponent(id)}/decide`, {
    method: "POST",
    body: JSON.stringify({ approve, reason }),
  });
}

// ─── Chat request classification (Phase 14) ────────────────────────────────
// The classifier lives in the runtime; the front door calls it rather than
// re-implementing the rules (one runtime, ADR-H117). Both routes are read-only.

export type CodeIntentVerdict = "code_change" | "code_question" | "not_code";

export interface CodeIntent {
  verdict: CodeIntentVerdict;
  confidence: "certain" | "likely";
  reason: string;
  signals: string[];
}

export async function classifyCodeIntent(
  query: string,
  history: Array<{ role: "user" | "assistant"; content: string }> = [],
): Promise<CodeIntent> {
  const body = await request<{ intent: CodeIntent }>("/code/intent", {
    method: "POST",
    body: JSON.stringify({ query, history }),
    timeoutMs: 10_000,
  });
  return body.intent;
}

/** The runtime's server-resolved code root. Read-only; used by proxy routes. */
export async function getCodeRoot(): Promise<string | null> {
  try {
    const body = await request<{ root: string | null; available: boolean }>("/code/root", {
      method: "GET",
      timeoutMs: 10_000,
    });
    return body.available ? body.root : null;
  } catch {
    return null;
  }
}



// ─── Workspace folders (folder picker) ─────────────────────────────────────
// Thin proxy over the runtime's /workspace routes. Approving a folder is the one
// way a new root becomes workable; selecting it makes it the active workspace.

export interface BrowseEntry {
  name: string;
  path: string;
  isDir: boolean;
  hidden: boolean;
}

export interface BrowseResult {
  path: string | null;
  parent: string | null;
  entries: BrowseEntry[];
  truncated: boolean;
  reason: string | null;
}

export interface TrustedRoot {
  id: string;
  path: string;
  label: string | null;
  createdAt: string;
  lastUsedAt: string | null;
  selected: boolean;
}

export async function browseFolders(path?: string): Promise<BrowseResult> {
  const q = path ? `?path=${encodeURIComponent(path)}` : "";
  const body = await request<BrowseResult & { success: boolean }>(`/workspace/browse${q}`, {
    method: "GET",
    timeoutMs: 15_000,
  });
  return body;
}

export async function listTrustedRoots(): Promise<TrustedRoot[]> {
  const body = await request<{ roots: TrustedRoot[] }>("/workspace/roots", { method: "GET" });
  return body.roots ?? [];
}

export async function approveTrustedRoot(path: string, label?: string): Promise<TrustedRoot> {
  const body = await request<{ root: TrustedRoot }>("/workspace/roots", {
    method: "POST",
    body: JSON.stringify({ path, label }),
  });
  return body.root;
}

export async function selectTrustedRoot(rootId: string | null): Promise<TrustedRoot | null> {
  const body = await request<{ selected: TrustedRoot | null }>("/workspace/roots/select", {
    method: "POST",
    body: JSON.stringify({ rootId }),
  });
  return body.selected;
}

export async function revokeTrustedRoot(rootId: string): Promise<void> {
  await request(`/workspace/roots/${encodeURIComponent(rootId)}`, { method: "DELETE" });
}

// ─── Editor: file tree + read + write ───────────────────────────────────────

export interface EditorEntry {
  name: string;
  path: string;
  isDir: boolean;
}

export interface EditorTreeResult {
  root: string;
  path: string;
  entries: EditorEntry[];
  truncated: boolean;
}

export interface EditorFileResult {
  path: string;
  content: string;
  redacted: boolean;
  lines: number;
}

export async function listWorkspaceFiles(path = "."): Promise<EditorTreeResult> {
  const body = await request<EditorTreeResult & { success: boolean }>(
    `/workspace/files?path=${encodeURIComponent(path)}`,
    { method: "GET", timeoutMs: 20_000 },
  );
  return body;
}

export async function readWorkspaceFile(path: string): Promise<EditorFileResult> {
  const body = await request<EditorFileResult & { success: boolean }>("/workspace/file/read", {
    method: "POST",
    body: JSON.stringify({ path }),
    timeoutMs: 20_000,
  });
  return body;
}

export async function writeWorkspaceFile(path: string, content: string): Promise<{ path: string; bytes: number }> {
  const body = await request<{ success: boolean; path: string; bytes: number }>("/workspace/file/write", {
    method: "POST",
    body: JSON.stringify({ path, content }),
    timeoutMs: 30_000,
  });
  return { path: body.path, bytes: body.bytes };
}

export async function makeWorkspaceFolder(path: string): Promise<{ path: string }> {
  const body = await request<{ success: boolean; path: string }>("/workspace/file/mkdir", {
    method: "POST",
    body: JSON.stringify({ path }),
    timeoutMs: 20_000,
  });
  return { path: body.path };
}

export async function deleteWorkspacePath(path: string): Promise<{ path: string; removed: boolean }> {
  const body = await request<{ success: boolean; path: string; removed: boolean }>("/workspace/file/delete", {
    method: "POST",
    body: JSON.stringify({ path }),
    timeoutMs: 20_000,
  });
  return { path: body.path, removed: body.removed };
}

// ─── Code-verification wire types (Phase 4) ─────────────────────────────────
// Mirror of the Python `code/verify.py` shapes. This module holds NO agentic
// logic — the panel renders what the runtime recorded, and never upgrades an
// unsupported claim.

export type CheckClaimKind = "tests_pass" | "typecheck_clean" | "build_ok" | "lint_clean";

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
  status: "passed" | "unrepairable" | "budget_exhausted" | "refused" | "no_checks";
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

/**
 * The ONLY place a claim's status word is chosen. A claim that is not supported
 * can never be reported as verified — the panel calls this, so "verified" and an
 * unsupported claim can never coincide.
 */
export function claimStatusKey(supported: boolean): 'code.proof.verified' | 'code.proof.notChecked' {
  return supported ? 'code.proof.verified' : 'code.proof.notChecked';
}

/** Narrow an unknown run field to a CodeVerification blob, or null. */
export function coerceCodeVerification(raw: unknown): CodeVerification | null {
  if (raw === null || typeof raw !== "object") return null;
  const blob = raw as Record<string, unknown>;
  const records = Array.isArray(blob.records) ? (blob.records as CodeVerificationRecord[]) : [];
  const claims = Array.isArray(blob.claims) ? (blob.claims as CodeVerificationClaim[]) : [];
  if (records.length === 0 && claims.length === 0 && !blob.repair) return null;
  return {
    runId: String(blob.runId ?? ""),
    records,
    claims,
    unverifiedCount: Number(blob.unverifiedCount ?? 0),
    repair: (blob.repair as CodeVerificationRepair | null) ?? null,
    truncated: Boolean(blob.truncated),
  };
}
