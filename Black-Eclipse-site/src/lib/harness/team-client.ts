// ─── Bot Team Orchestration client ────────────────────────────────────────────
// The typed front door to the runtime's `/team/*` routes. It carries no
// orchestration logic: it starts a team run, reads its status, result and review.
// The chatbot remains the primary interface; this is for a programmatic caller or
// a future panel.

export type TeamSubtaskStatus =
  | "PENDING" | "READY" | "RUNNING" | "BLOCKED"
  | "COMPLETED" | "FAILED" | "CANCELLED" | "SKIPPED";

export type TeamRunStatus =
  | "PLANNING" | "RUNNING" | "REVIEWING" | "REPAIRING"
  | "COMPLETED" | "PARTIAL" | "FAILED" | "CANCELLED";

export type ReviewOutcome =
  | "APPROVED" | "APPROVED_WITH_LIMITATIONS" | "REVISION_REQUIRED"
  | "REJECTED" | "UNABLE_TO_VERIFY";

export interface TeamMemberView {
  agentId: string;
  role?: string;
  capabilities?: string[];
  maxConcurrency?: number;
  tools?: string[] | null;
  instructions?: string;
  label?: string | null;
}

export interface TeamSubtaskView {
  id: string;
  objective: string;
  capability?: string;
  assignedAgentId?: string | null;
  dependsOn?: string[];
  required?: boolean;
  expectedOutput?: Record<string, unknown>;
  inputRefs?: string[];
  deadlineMs?: number | null;
  budget?: Record<string, unknown>;
  review?: boolean;
  priority?: string;
}

export interface TeamPolicyView {
  delegationEnabled?: boolean;
  maxDepth?: number;
  maxChildren?: number;
  maxConcurrency?: number;
  perAgentConcurrency?: number;
  maxTasks?: number;
  maxCost?: number;
  maxRuntimeMs?: number;
  requireReview?: boolean;
  reviewStrictness?: "NONE" | "LENIENT" | "STANDARD" | "STRICT";
  optionalFailurePolicy?: "ALLOW_PARTIAL" | "REQUIRE_ALL";
  allowedProviders?: string[];
  requireApproval?: boolean;
}

export interface TeamDefinitionView {
  id: string;
  name: string;
  objective?: string;
  agentId?: string;
  members: TeamMemberView[];
  subtasks: TeamSubtaskView[];
  policy?: TeamPolicyView;
  metadata?: Record<string, unknown>;
}

export interface TeamRunView {
  id: string;
  teamId: string;
  name: string;
  rootRunId: string;
  planId?: string | null;
  status: TeamRunStatus;
  subtaskTaskIds: Record<string, string>;
  repairTaskIds: string[];
  memberAgents: string[];
  reviewRequired: boolean;
  attempts: number;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
  finishedAt?: string | null;
}

export interface TeamSubtaskStateView {
  subtaskId: string;
  taskId: string;
  agentId?: string | null;
  status: string;
  title: string;
  error?: string | null;
}

export interface TeamStatusView {
  team: TeamRunView;
  subtasks: TeamSubtaskStateView[];
  repairTaskIds: string[];
}

export interface TeamConflictView {
  id: string;
  subject: string;
  kind: string;
  status: "RESOLVED" | "EXPLAINED" | "UNRESOLVED";
  material: boolean;
  findingIds: string[];
  evidenceRefs: string[];
  resolutionMethod?: string;
  residualUncertainty?: string;
  detail?: string;
}

export interface ReviewFindingView {
  id: string;
  subtaskId?: string | null;
  criterion: string;
  severity: "BLOCKING" | "ADVISORY";
  detail: string;
  evidenceRefs: string[];
  repairInstruction: string;
}

export interface TeamReviewView {
  outcome: ReviewOutcome;
  findings: ReviewFindingView[];
  reviewerAgentId: string;
  independent: boolean;
  attempts: number;
  notes: string[];
}

export interface TeamReviewResult {
  status: string;
  teamRunId: string;
  planId?: string | null;
  review: TeamReviewView | null;
  reviewOutcome: ReviewOutcome | null;
  conflicts: TeamConflictView[];
  unresolvedConflicts: TeamConflictView[];
  unsupportedFindingIds: string[];
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/team${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: { message?: string }; error?: string }) ?? {};
    throw new Error(detail.detail?.message ?? detail.error ?? `team request failed (${res.status})`);
  }
  return data as T;
}

export async function startTeam(
  team: TeamDefinitionView,
  options: { modelSettings?: Record<string, unknown>; rootRunId?: string } = {},
): Promise<TeamRunView> {
  const data = await call<{ teamRun: TeamRunView }>("/runs", {
    method: "POST",
    body: JSON.stringify({ team, ...options }),
  });
  return data.teamRun;
}

export async function listTeamRuns(status?: string): Promise<TeamRunView[]> {
  const data = await call<{ runs: TeamRunView[] }>(`/runs${status ? `?status=${status}` : ""}`);
  return data.runs;
}

export async function getTeamRun(runId: string): Promise<TeamStatusView> {
  const data = await call<{ teamRun: TeamStatusView }>(`/runs/${runId}`);
  return data.teamRun;
}

export async function getTeamResult(runId: string): Promise<string> {
  const data = await call<{ result: string }>(`/runs/${runId}/result`);
  return data.result;
}

export async function reviewTeam(runId: string, reviewerAgentId = "qa-agent"): Promise<TeamReviewResult> {
  const data = await call<{ review: TeamReviewResult }>(`/runs/${runId}/review`, {
    method: "POST",
    body: JSON.stringify({ reviewerAgentId }),
  });
  return data.review;
}

export async function cancelTeam(runId: string): Promise<{ cancelledTaskIds: string[] }> {
  const data = await call<{ cancel: { cancelledTaskIds: string[] } }>(`/runs/${runId}/cancel`, {
    method: "POST",
  });
  return data.cancel;
}
