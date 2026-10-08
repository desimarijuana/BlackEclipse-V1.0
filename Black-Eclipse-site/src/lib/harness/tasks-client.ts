// ─── Task / Plan front door ──────────────────────────────────────────────────
// A thin, typed client over the Python runtime's /tasks and /plans routes. It
// adds NO task logic (the durable store in `python/harness/tasks/` is the source
// of truth): it validates shapes, forwards, and returns what the runtime owns.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";

export type TaskStatus =
  | "TODO" | "IN_PROGRESS" | "BLOCKED" | "WAITING"
  | "FAILED" | "COMPLETED" | "CANCELLED";

export type PlanStatus =
  | "PLANNING" | "READY" | "RUNNING" | "BLOCKED"
  | "COMPLETED" | "FAILED" | "CANCELLED";

export type TaskPriority = "LOW" | "NORMAL" | "HIGH" | "URGENT" | "CRITICAL";
export type DependencyKind = "BLOCKS" | "REQUIRES" | "OPTIONAL";
export type CriterionState = "PENDING" | "PASSED" | "FAILED";

export interface Plan {
  id: string;
  name: string;
  description: string;
  objective: string;
  rootTaskId: string | null;
  status: PlanStatus;
  priority: TaskPriority;
  agentId: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface AcceptanceCriterion {
  id: string;
  taskId: string;
  text: string;
  state: CriterionState;
  evidence: string | null;
  required: boolean;
}

export interface TaskDependency {
  id: string;
  taskId: string;
  dependsOnTaskId: string;
  kind: DependencyKind;
}

export interface TaskArtifact {
  id: string;
  taskId: string;
  kind: string;
  uri: string;
  digest: string | null;
  label: string | null;
}

export interface TaskExecution {
  id: string;
  taskId: string;
  attempt: number;
  agentId: string | null;
  runId: string | null;
  status: string;
  error: string | null;
  errorClass: string | null;
  startedAt: string;
  completedAt: string | null;
}

export interface TaskNode {
  id: string;
  planId: string | null;
  parentTaskId: string | null;
  title: string;
  description: string;
  objective: string;
  status: TaskStatus;
  priority: TaskPriority;
  progress: number;
  assignedAgentId: string | null;
  assignedRunId: string | null;
  retryCount: number;
  maxRetries: number;
  waitingReason: string | null;
  blockedReason: string | null;
  blockedBy: string[];
  error: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  criteria?: AcceptanceCriterion[];
  dependencies?: TaskDependency[];
  artifacts?: TaskArtifact[];
  executions?: TaskExecution[];
  executionCount?: number;
  completionFailures?: string[];
  runnable?: boolean;
  children: TaskNode[];
}

export interface PlanView {
  plan: Plan;
  stats: {
    total: number;
    byStatus: Record<string, number>;
    runnable: number;
    progress: number;
  };
  tasks: TaskNode[];
}

export interface CreatePlanInput {
  name: string;
  description?: string;
  objective?: string;
  priority?: TaskPriority;
  agentId?: string;
}

export interface CreateTaskInput {
  title: string;
  description?: string;
  objective?: string;
  planId?: string;
  parentTaskId?: string;
  priority?: TaskPriority;
  assignedAgentId?: string;
  dependencies?: string[];
  acceptanceCriteria?: Array<{ text: string; required?: boolean }>;
}

interface Envelope<T> {
  success: boolean;
  [key: string]: unknown;
}

export class TaskClientError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "TaskClientError";
  }
}

async function request<T>(path: string, method: string, body?: unknown): Promise<T> {
  if (!(await ensurePythonRuntime())) {
    throw new TaskClientError("The Python agent runtime is not available.", 503);
  }
  const token = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Harness-Operator": token } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(45_000),
  });
  const data = (await res.json().catch(() => ({}))) as Envelope<T> & { detail?: unknown };
  if (!res.ok) {
    const detail = data.detail;
    const message =
      typeof detail === "object" && detail && "message" in detail
        ? String((detail as { message: unknown }).message)
        : typeof detail === "string"
          ? detail
          : `task request failed (${res.status})`;
    throw new TaskClientError(message, res.status);
  }
  return data as T;
}

export const tasksClient = {
  listPlans: () => request<{ plans: Plan[] }>("/plans", "GET"),
  createPlan: (input: CreatePlanInput) => request<{ plan: Plan }>("/plans", "POST", input),
  getPlan: (planId: string) => request<{ plan: PlanView }>(`/plans/${planId}`, "GET"),
  planTasks: (planId: string) => request<{ tasks: TaskNode[] }>(`/plans/${planId}/tasks`, "GET"),
  startPlan: (planId: string) => request<{ plan: Plan }>(`/plans/${planId}/start`, "POST", {}),

  listTasks: (params: { planId?: string; parentTaskId?: string; status?: TaskStatus } = {}) => {
    const q = new URLSearchParams();
    if (params.planId) q.set("planId", params.planId);
    if (params.parentTaskId) q.set("parentTaskId", params.parentTaskId);
    if (params.status) q.set("status", params.status);
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return request<{ tasks: TaskNode[] }>(`/tasks${suffix}`, "GET");
  },
  createTask: (input: CreateTaskInput) => request<{ task: TaskNode }>("/tasks", "POST", input),
  getTask: (taskId: string) => request<{ task: TaskNode }>(`/tasks/${taskId}`, "GET"),
  taskTree: (taskId: string) => request<{ tree: TaskNode }>(`/tasks/${taskId}/tree`, "GET"),
  updateTask: (taskId: string, fields: Record<string, unknown>) =>
    request<{ task: TaskNode }>(`/tasks/${taskId}`, "PATCH", { fields }),
  completeTask: (taskId: string, force = false) =>
    request<{ task: TaskNode }>(`/tasks/${taskId}/complete`, "POST", { force }),
  cancelTask: (taskId: string, reason = "", cascade = true) =>
    request<{ cancelled: string[] }>(`/tasks/${taskId}/cancel`, "POST", { reason, cascade }),
  retryTask: (taskId: string) => request<{ task: TaskNode }>(`/tasks/${taskId}/retry`, "POST", {}),
  blockTask: (taskId: string, reason = "DEPENDENCY") =>
    request<{ task: TaskNode }>(`/tasks/${taskId}/block`, "POST", { reason }),
  unblockTask: (taskId: string) =>
    request<{ task: TaskNode }>(`/tasks/${taskId}/unblock`, "POST", {}),
  addDependency: (taskId: string, dependsOnTaskId: string, kind: DependencyKind = "REQUIRES") =>
    request<{ dependency: TaskDependency }>(`/tasks/${taskId}/dependencies`, "POST", {
      dependsOnTaskId,
      kind,
    }),
  removeDependency: (taskId: string, dependsOnTaskId: string) =>
    request<{ removed: boolean }>(`/tasks/${taskId}/dependencies/${dependsOnTaskId}`, "DELETE"),
  setCriterion: (criterionId: string, state: CriterionState, evidence?: string) =>
    request<{ criterion: AcceptanceCriterion }>(`/criteria/${criterionId}`, "PATCH", {
      state,
      evidence,
    }),
};

export type TasksClient = typeof tasksClient;
