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
