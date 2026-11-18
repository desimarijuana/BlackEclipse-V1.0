// ─── Task / Plan BROWSER client ──────────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/tasks/**`, `/api/plans/**`),
// which proxy to the Python runtime. This module MUST stay client-safe: no
// `child_process`, no `fs`, no `ensurePythonRuntime` (that lives in the
// server-only `tasks-client.ts`). Fetch only, so the screen mounts in a client
// component without pulling server code into the browser bundle.

import type {
  AcceptanceCriterion,
  CreatePlanInput,
  CreateTaskInput,
  CriterionState,
  DependencyKind,
  Plan,
  PlanView,
  TaskNode,
} from "./tasks-client";

// Type-only re-export — erased at compile time, so no server code ships.
export type {
  AcceptanceCriterion,
  CreatePlanInput,
  CreateTaskInput,
  CriterionState,
  DependencyKind,
  Plan,
  PlanView,
  TaskNode,
};

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & {
    error?: string;
    detail?: unknown;
  };
  if (!res.ok) {
    const detail = body.detail;
    const message =
      typeof detail === "object" && detail && "message" in detail
        ? String((detail as { message: unknown }).message)
        : typeof detail === "string"
          ? detail
          : body.error ?? `request failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

export async function listPlans(): Promise<Plan[]> {
  const body = await api<{ plans: Plan[] }>("/api/plans");
  return body.plans ?? [];
}

export async function createPlan(input: CreatePlanInput): Promise<Plan> {
  const body = await api<{ plan: Plan }>("/api/plans", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return body.plan;
}

export async function getPlan(planId: string): Promise<PlanView> {
  const body = await api<{ plan: PlanView }>(`/api/plans/${encodeURIComponent(planId)}`);
  return body.plan;
}

export async function startPlan(planId: string): Promise<Plan> {
  const body = await api<{ plan: Plan }>(`/api/plans/${encodeURIComponent(planId)}/start`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return body.plan;
}

export async function createTask(input: CreateTaskInput): Promise<TaskNode> {
  const body = await api<{ task: TaskNode }>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return body.task;
}

/** One task as the runtime projects it (live `assignedRunId` + executions). */
export async function getTask(taskId: string): Promise<TaskNode> {
  const body = await api<{ task: TaskNode }>(`/api/tasks/${encodeURIComponent(taskId)}`);
  return body.task;
}

export async function completeTask(taskId: string, force = false): Promise<TaskNode> {
  const body = await api<{ task: TaskNode }>(
    `/api/tasks/${encodeURIComponent(taskId)}/complete`,
    { method: "POST", body: JSON.stringify({ force }) },
  );
  return body.task;
}

export async function cancelTask(taskId: string): Promise<string[]> {
  const body = await api<{ cancelled: string[] }>(
    `/api/tasks/${encodeURIComponent(taskId)}/cancel`,
    { method: "POST", body: JSON.stringify({ cascade: true }) },
  );
  return body.cancelled ?? [];
}

export async function retryTask(taskId: string): Promise<TaskNode> {
  const body = await api<{ task: TaskNode }>(`/api/tasks/${encodeURIComponent(taskId)}/retry`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return body.task;
}

export async function blockTask(taskId: string, reason = "DEPENDENCY"): Promise<TaskNode> {
  const body = await api<{ task: TaskNode }>(`/api/tasks/${encodeURIComponent(taskId)}/block`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  return body.task;
}

export async function unblockTask(taskId: string): Promise<TaskNode> {
  const body = await api<{ task: TaskNode }>(
    `/api/tasks/${encodeURIComponent(taskId)}/unblock`,
    { method: "POST", body: JSON.stringify({}) },
  );
  return body.task;
}

export async function addDependency(
  taskId: string,
  dependsOnTaskId: string,
  kind: DependencyKind = "REQUIRES",
): Promise<void> {
  await api(`/api/tasks/${encodeURIComponent(taskId)}/dependencies`, {
    method: "POST",
    body: JSON.stringify({ dependsOnTaskId, kind }),
  });
}

export async function removeDependency(
  taskId: string,
  dependsOnTaskId: string,
): Promise<void> {
  await api(
    `/api/tasks/${encodeURIComponent(taskId)}/dependencies/${encodeURIComponent(dependsOnTaskId)}`,
    { method: "DELETE" },
  );
}

export async function setCriterion(
  criterionId: string,
  state: CriterionState,
  evidence?: string,
): Promise<AcceptanceCriterion> {
  const body = await api<{ criterion: AcceptanceCriterion }>(
    `/api/criteria/${encodeURIComponent(criterionId)}`,
    { method: "PATCH", body: JSON.stringify({ state, evidence }) },
  );
  return body.criterion;
}
