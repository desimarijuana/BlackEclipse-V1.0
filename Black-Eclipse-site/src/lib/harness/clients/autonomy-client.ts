// ─── W4 autonomy front door client ───────────────────────────────────────────
// Thin, typed proxy over the Python runtime's /goals and /loops routes. Adds no
// loop, no scheduling and no model call: it validates and forwards. Every
// mutating route is operator-gated by transport/token, never a body boolean.

import { HARNESS_PY_URL, ensurePythonRuntime } from "../python-runtime";
import { runtimeCallbackToken } from "../runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "../errors";

export type AutonomyMode = "off" | "shadow" | "on";
export type GoalStatus =
  | "active" | "paused" | "completed" | "failed" | "blocked" | "cancelled";
export type GoalVerdictKind = "done" | "continue" | "blocked" | "wait";
export type LoopKind = "loop" | "heartbeat";
export type LoopMode = "fixed" | "self_paced";
export type LoopStatus = "active" | "paused" | "cancelled" | "completed";

export interface GoalGateView {
  id: string;
  check: string;
  args?: Record<string, unknown>;
  workspaceId?: string | null;
  timeoutSeconds?: number;
  retries?: number;
}

export interface GoalVerdictView {
  id?: string;
  goalId: string;
  runId?: string | null;
  turn: number;
  verdict: GoalVerdictKind;
  reason: string;
  evidence: string[];
  gateResults: Array<{
    gateId: string;
    check: string;
    ok: boolean;
    exitCode?: number | null;
    timedOut?: boolean;
    durationMs?: number;
    outputTail?: string;
    errorCode?: string;
  }>;
  usage: Record<string, unknown>;
  createdAt?: string;
  nextStep?: string;
  wakeAt?: string;
  downgraded?: boolean;
  invalid?: boolean;
}

export interface GoalView {
  id: string;
  objective: string;
  acceptance: string[];
  planId: string | null;
  taskId: string | null;
  status: GoalStatus;
  budget: Record<string, unknown>;
  contract: Record<string, unknown> | null;
  gates: GoalGateView[];
  maxTurns: number;
  usedTurns: number;
  lastVerdict: GoalVerdictView | null;
  sessionId: string | null;
  nextRunAt: string | null;
  noProgress: number;
  modelProvider: string | null;
  modelName: string | null;
  workspaceId: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface LoopView {
  id: string;
  sessionId: string;
  kind: LoopKind;
  prompt: string;
  mode: LoopMode;
  intervalSeconds: number;
  nextTickAt: string | null;
  lastTickAt: string | null;
  maxTicks: number;
  usedTicks: number;
  noChangeCount: number;
  lastDigest: string | null;
  lastRunId: string | null;
  status: LoopStatus;
  modelProvider: string | null;
  modelName: string | null;
  workspaceId: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface AutonomyHealth {
  mode: AutonomyMode;
  goals: { total: number; byStatus: Record<string, number> };
  loops: { total: number; active: number; kinds: Record<string, number> };
}

export interface CreateGoalInput {
  objective: string;
  acceptance?: string[];
  constraints?: string[];
  deliverables?: string[];
  boundaries?: string[];
  stopWhen?: string[];
  gates?: GoalGateView[];
  maxTurns?: number;
  sessionId?: string;
  workspaceId?: string;
  autonomy?: "plan_only" | "edit_verify" | "approve_external";
  model?: { provider?: string; model?: string; baseUrl?: string };
  start?: boolean;
}

export interface CreateLoopInput {
  sessionId: string;
  kind?: LoopKind;
  prompt: string;
  intervalSeconds?: number;
  mode?: LoopMode;
  maxTicks?: number;
  workspaceId?: string;
  model?: { provider?: string; model?: string; baseUrl?: string };
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
    const raw = (body as { detail?: unknown }).detail;
    const detail =
      typeof raw === "string"
        ? raw
        : raw && typeof raw === "object" && "message" in raw
          ? String((raw as { message: unknown }).message)
          : `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

// ── Goals ─────────────────────────────────────────────────────────────────────
export async function createGoal(input: CreateGoalInput): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>("/goals", {
    method: "POST",
    body: JSON.stringify(input),
    timeoutMs: 60_000,
  });
  return body.goal;
}

export async function listGoals(params: { sessionId?: string; status?: string } = {}): Promise<GoalView[]> {
  const query = new URLSearchParams();
  if (params.sessionId) query.set("sessionId", params.sessionId);
  if (params.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const body = await request<{ goals: GoalView[] }>(`/goals${suffix}`, { method: "GET" });
  return body.goals ?? [];
}

export async function getGoal(id: string): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/goals/${encodeURIComponent(id)}`, { method: "GET" });
  return body.goal;
}

export async function goalVerdicts(id: string): Promise<GoalVerdictView[]> {
  const body = await request<{ verdicts: GoalVerdictView[] }>(
    `/goals/${encodeURIComponent(id)}/verdicts`,
    { method: "GET" },
  );
  return body.verdicts ?? [];
}

export async function pauseGoal(id: string, reason = ""): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/goals/${encodeURIComponent(id)}/pause`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  return body.goal;
}

export async function resumeGoal(id: string): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/goals/${encodeURIComponent(id)}/resume`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return body.goal;
}

export async function cancelGoal(id: string): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/goals/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return body.goal;
}

// ── Loops / heartbeats ────────────────────────────────────────────────────────
export async function createLoop(input: CreateLoopInput): Promise<LoopView> {
  const body = await request<{ loop: LoopView }>("/loops", {
    method: "POST",
    body: JSON.stringify(input),
    timeoutMs: 60_000,
  });
  return body.loop;
}

export async function listLoops(params: { sessionId?: string; status?: string } = {}): Promise<LoopView[]> {
  const query = new URLSearchParams();
  if (params.sessionId) query.set("sessionId", params.sessionId);
  if (params.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const body = await request<{ loops: LoopView[] }>(`/loops${suffix}`, { method: "GET" });
  return body.loops ?? [];
}

export async function pauseLoop(id: string, reason = ""): Promise<LoopView> {
  const body = await request<{ loop: LoopView }>(`/loops/${encodeURIComponent(id)}/pause`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  return body.loop;
}

export async function resumeLoop(id: string): Promise<LoopView> {
  const body = await request<{ loop: LoopView }>(`/loops/${encodeURIComponent(id)}/resume`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return body.loop;
}

export async function cancelLoop(id: string): Promise<LoopView> {
  const body = await request<{ loop: LoopView }>(`/loops/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return body.loop;
}

export async function getAutonomyHealth(): Promise<AutonomyHealth> {
  const body = await request<{ health: AutonomyHealth }>("/autonomy/health", { method: "GET" });
  return body.health;
}
