// ─── Evolution (self-improvement) front door (Phase 10) ─────────────────────
// Thin, typed proxy over the Python runtime's /evolution routes. Adds NO agentic
// logic (mirrors code-client.ts): it validates, forwards, and returns what the
// runtime owns. Operator-gated routes present the runtime secret by
// transport/token, never a body boolean.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type EvolutionStatus =
  | "inert" | "proposed" | "refused" | "evaluating" | "evaluated_ok"
  | "evaluated_bad" | "canaried" | "activated" | "rolled_back" | "dismissed";

export interface EvolutionCandidate {
  id: string;
  signature: string;
  sourceCategory: string;
  observedCount: number;
  problemStatement: string;
  targetPath: string | null;
  proposedOps?: Array<Record<string, unknown>> | null;
  subjectType?: "code" | "surface";
  surfaceConfig?: Record<string, unknown> | null;
  createdByRunId?: string | null;
  status: EvolutionStatus;
  refusalCode: string | null;
  activatedVersion: string | null;
  previousVersion: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface EvolutionAttempt {
  id: string;
  candidateId: string;
  attemptIndex: number;
  targetPath: string;
  diffDigest: string;
  outcome: "success" | "failure" | "rolled_back" | "refused";
  outcomeReason: string | null;
  costMicros: number | null;
  tokensUsed: number | null;
  evaluation: Record<string, unknown> | null;
  startedAt: string;
  finishedAt: string | null;
}

export interface EvolutionExperiment {
  id: string;
  suite: string;
  datasetName: string;
  datasetVersion: string;
  status: string;
  trialCount: number;
  agentVersion: string | null;
  gitCommit: string | null;
  model: string | null;
  provider: string | null;
  startedAt: string;
  finishedAt: string | null;
  config: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface EvolutionExperimentMetric {
  id: string;
  runId: string;
  scope: string;
  category: string;
  dimension: string;
  value: number | null;
  sampleSize: number;
  createdAt: string;
}

export interface EvolutionExperimentTrial {
  id: string;
  runId: string;
  taskId: string;
  taskVersion: number;
  trialIndex: number;
  passed: number | boolean;
  unmeasured: number | boolean;
  status: string;
  score: Record<string, unknown> | null;
  cost: number;
  latencyMs: number | null;
  totalTokens: number;
  createdAt: string;
}

export interface EvolutionExperimentDetail {
  experiment: EvolutionExperiment;
  metrics: EvolutionExperimentMetric[];
  trials: EvolutionExperimentTrial[];
}

export interface EvolutionCandidateEvidence {
  candidate: EvolutionCandidate;
  attempts: EvolutionAttempt[];
  experiments: EvolutionExperiment[];
}

export interface EvolutionLandingResult {
  success: boolean;
  candidateId: string;
  runId: string;
  preview: Record<string, unknown>;
  landing: Record<string, unknown>;
  approvalRequired: boolean;
  promotionRoute: string;
}

export interface EvolutionRslStatus {
  mode: "off" | "observe" | "propose" | "verify" | string;
  running: boolean;
  busy: boolean;
  maxCandidates: number;
  maxExperimentsPerDay: number;
  k: number;
  startedToday: number;
  remainingToday: number;
  budgetExhausted: boolean;
  tickSeconds?: number;
  leaseSeconds?: number;
  trials?: number;
  maxCostUsd?: number;
}

export interface EvolutionRslTickResult {
  success: boolean;
  mode: string;
  processed: string[];
  skipped?: string;
  candidateId?: string;
  runId?: string;
  decision?: string;
  benchmark?: string;
}

export interface EvolutionProposeInput {
  targetPath?: string | null;
  ops: Array<Record<string, unknown>>;
}

export interface EvolutionProposeResult {
  success: boolean;
  candidate: EvolutionCandidate;
}

export interface EvolutionMetrics {
  attempts: number;
  successRate: number | "UNKNOWN";
  regressionRate: number | "UNKNOWN";
  rollbackCount: number;
  costPerSuccess: number | "UNKNOWN";
  cost_per_success: number | "UNKNOWN";
  regression_rate: number | null;
  rsl_experiments: number | null;
  rsl_accepted: number | null;
  rsl_rejected: number | null;
  rsl_unmeasured: number | null;
  perCategory: Record<string, { attempts: number; successes: number; rollbacks: number }>;
  unmeasured: string[];
}

export interface EvolutionLesson {
  id: string;
  cue: string | null;
  proposedLesson: string | null;
  evidenceReferences: unknown;
  scope: Record<string, unknown> | string | null;
  adoptedArtifactType: string | null;
  adoptedArtifactId: string | null;
  validationRunId: string | null;
  status: string;
  sourceRunId: string | null;
  confidence: number;
  createdAt: string;
}

export interface EvolutionLessonInput {
  cue: string;
  lesson: string;
  evidence?: unknown;
  scope?: Record<string, unknown> | null;
  validationRunId: string;
  adoptedArtifactType?: string | null;
  adoptedArtifactId?: string | null;
}

export interface EvolutionRecursiveVariant {
  kind: "invariant" | "domain";
  targetPath?: string | null;
  ops: Array<Record<string, unknown>>;
  description?: string;
}

export interface EvolutionRecursiveResult {
  success: boolean;
  runId: string;
  k: number;
  requestedK: number;
  benchmark: string;
  selection: Record<string, unknown> | null;
  composition: Record<string, unknown> | null;
  variants: Array<Record<string, unknown>>;
  children: EvolutionCandidate[];
}

export interface EvolutionSurfaceSnapshot {
  systemPrompt: string;
  toolNames?: string[];
  maxSteps?: number;
  maxToolCalls?: number;
  modelProvider?: string | null;
  modelName?: string | null;
  temperature?: number | null;
  skillDraftIds?: string[];
}

export interface EvolutionSurfaceExperimentInput {
  candidate: EvolutionSurfaceSnapshot;
  base?: EvolutionSurfaceSnapshot;
  dataset?: string;
  taskIds?: string[];
  split?: "optimization" | "validation" | "held_out" | "release";
  targetDimension?: string;
  trials?: number;
  seed?: number;
  baselineRunId?: string | null;
  problemStatement?: string;
  sourceCategory?: string;
}

export interface EvolutionSurfaceExperimentResult {
  success: boolean;
  candidate: EvolutionCandidate;
  created: boolean;
  queued: boolean;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(600_000),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

export async function listEvolutionCandidates(): Promise<EvolutionCandidate[]> {
  const body = await request<{ candidates: EvolutionCandidate[] }>("/evolution/candidates", { method: "GET" });
  return body.candidates ?? [];
}

export async function getEvolutionCandidate(id: string): Promise<EvolutionCandidate> {
  const body = await request<{ candidate: EvolutionCandidate }>(
    `/evolution/candidates/${encodeURIComponent(id)}`, { method: "GET" },
  );
  return body.candidate;
}

export async function listEvolutionAttempts(id: string): Promise<EvolutionAttempt[]> {
  const body = await request<{ attempts: EvolutionAttempt[] }>(
    `/evolution/candidates/${encodeURIComponent(id)}/attempts`, { method: "GET" },
  );
  return body.attempts ?? [];
}

export async function evaluateEvolutionCandidate(id: string): Promise<unknown> {
  return request(`/evolution/candidates/${encodeURIComponent(id)}/evaluate`, { method: "POST", body: "{}" });
}

export async function activateEvolutionCandidate(id: string, canary = false): Promise<unknown> {
  return request(`/evolution/candidates/${encodeURIComponent(id)}/activate`, {
    method: "POST", body: JSON.stringify({ canary }),
  });
}

export async function rollbackEvolutionCandidate(id: string, reason = ""): Promise<unknown> {
  return request(`/evolution/candidates/${encodeURIComponent(id)}/rollback`, {
    method: "POST", body: JSON.stringify({ reason }),
  });
}

export async function dismissEvolutionCandidate(id: string): Promise<unknown> {
  return request(`/evolution/candidates/${encodeURIComponent(id)}/dismiss`, { method: "POST" });
}

export async function listEvolutionExperiments(limit = 50): Promise<EvolutionExperiment[]> {
  const body = await request<{ experiments: EvolutionExperiment[] }>(
    `/evolution/experiments?limit=${encodeURIComponent(String(limit))}`, { method: "GET" },
  );
  return body.experiments ?? [];
}

export async function getEvolutionExperiment(id: string): Promise<EvolutionExperimentDetail> {
  const body = await request<EvolutionExperimentDetail>(
    `/evolution/experiments/${encodeURIComponent(id)}`, { method: "GET" },
  );
  return body;
}

export async function evolutionCandidateEvidence(id: string): Promise<EvolutionCandidateEvidence> {
  return request<EvolutionCandidateEvidence>(
    `/evolution/candidates/${encodeURIComponent(id)}/evidence`, { method: "GET" },
  );
}

export async function prepareEvolutionLanding(id: string): Promise<EvolutionLandingResult> {
  return request<EvolutionLandingResult>(
    `/evolution/candidates/${encodeURIComponent(id)}/prepare-landing`, { method: "POST" },
  );
}

export async function listEvolutionLessons(limit = 50): Promise<EvolutionLesson[]> {
  const body = await request<{ lessons: EvolutionLesson[] }>(
    `/evolution/lessons?limit=${encodeURIComponent(String(limit))}`, { method: "GET" },
  );
  return body.lessons ?? [];
}

export async function adoptEvolutionLesson(
  candidateId: string, input: EvolutionLessonInput,
): Promise<{ stored: boolean; duplicate?: boolean; lesson: EvolutionLesson }> {
  return request(
    `/evolution/candidates/${encodeURIComponent(candidateId)}/lessons`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function runEvolutionRecursive(
  candidateId: string, input: { variants: EvolutionRecursiveVariant[]; seed?: number },
): Promise<EvolutionRecursiveResult> {
  return request<EvolutionRecursiveResult>(
    `/evolution/candidates/${encodeURIComponent(candidateId)}/recursive`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function proposeEvolutionCandidate(
  candidateId: string, input: EvolutionProposeInput,
): Promise<EvolutionProposeResult> {
  return request<EvolutionProposeResult>(
    `/evolution/candidates/${encodeURIComponent(candidateId)}/propose`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getEvolutionRslStatus(): Promise<EvolutionRslStatus> {
  return request<EvolutionRslStatus>("/evolution/rsl", { method: "GET" });
}

export async function tickEvolutionRsl(): Promise<EvolutionRslTickResult> {
  return request<EvolutionRslTickResult>("/evolution/rsl/tick", { method: "POST" });
}

export async function createEvolutionSurfaceExperiment(
  input: EvolutionSurfaceExperimentInput,
): Promise<EvolutionSurfaceExperimentResult> {
  return request<EvolutionSurfaceExperimentResult>(
    "/evolution/surface-experiments",
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function evolutionMetrics(): Promise<EvolutionMetrics> {
  return request<EvolutionMetrics>("/evolution/metrics", { method: "GET" });
}

/** The plain state key for a candidate. The ONE place a state word is chosen. */
export function evolutionStateKey(status: EvolutionStatus): string {
  return `evolution.state.${status}`;
}

/** A metric rendered as a number or the honest "not measured" value. */
export function metricLabel(value: number | "UNKNOWN"): string {
  return value === "UNKNOWN" ? "not measured yet" : String(value);
}
