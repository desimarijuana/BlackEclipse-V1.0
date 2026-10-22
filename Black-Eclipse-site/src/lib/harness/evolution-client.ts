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
  subjectType?: "code" | "surface" | "drift";
  scope?: string | null;
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
  objective?: "single" | "pareto" | string;
  strategy?: string;
  generations?: number;
  climbSeconds?: number;
  climbScope?: string;
  climbPaused?: boolean;
  climbEnabled?: boolean;
  nextClimbInSeconds?: number | null;
  lastClimb?: Record<string, unknown> | null;
  driftWatch?: {
    enabled: boolean;
    intervalSeconds: number;
    running: boolean;
    last: Record<string, string>;
  };
  tickSeconds?: number;
  leaseSeconds?: number;
  trials?: number;
  maxCostUsd?: number;
}

export interface EvolutionRslDigest {
  days: number;
  since: string;
  experiments: {
    rsl_experiments: number | null;
    rsl_accepted: number | null;
    rsl_rejected: number | null;
    rsl_unmeasured: number | null;
    regression_rate: number | null;
    cost_usd: number | null;
    cost_per_accepted: number | null;
  };
  candidates: Record<string, number>;
  recentCandidates: Array<{
    id: string;
    status: string;
    subjectType?: string;
    sourceCategory?: string;
    createdAt?: string;
  }>;
  lessons: Array<{ id: string; cue: string; lesson: string; createdAt?: string }>;
  drift: {
    scope?: string;
    status?: string;
    drop?: number | null;
    window?: number;
    minSamples?: number;
  };
}

export interface EvolutionRslReport {
  success: boolean;
  digest: EvolutionRslDigest;
  markdown: string;
}

export interface EvolutionRslTickResult {
  success: boolean;
  mode: string;
  processed: string[];
  skipped?: string;
  candidateId?: string;
  runId?: string;
  stateId?: string | null;
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

export interface EvolutionHarnessState {
  id: string;
  parentStateId: string | null;
  scope: string;
  snapshotDigest: string;
  candidateId: string | null;
  acceptedRunId: string | null;
  utility: number | null;
  metrics: Record<string, unknown>;
  status: "candidate" | "current" | "superseded" | "retired" | string;
  createdAt: string;
  promotedAt: string | null;
}

export interface EvolutionHarnessStates {
  scope: string;
  current: EvolutionHarnessState | null;
  currents: EvolutionHarnessState[];
  states: EvolutionHarnessState[];
}

export interface EvolutionParetoState {
  id: string | null;
  scope: string | null;
  status: string | null;
  utility: number | null;
  vector: Record<string, number | null>;
}

export interface EvolutionPareto {
  objectives: Record<string, "max" | "min" | string>;
  frontier: string[];
  dominated: Record<string, string>;
  states: EvolutionParetoState[];
}

export interface EvolutionLessonStats {
  lessonId: string;
  injected: number;
  injectedSuccesses: number;
  injectedRate: number | null;
  injectedCiLow: number | null;
  injectedCiHigh: number | null;
  control: number;
  controlSuccesses: number;
  controlRate: number | null;
  controlCiLow: number | null;
  controlCiHigh: number | null;
  lift: number | null;
  status: "measured" | "insufficient" | "unmeasured" | string;
  reason: string;
}

export interface EvolutionLessonOutcome {
  id: string;
  lessonId: string;
  runId: string;
  injected: number;
  outcome: "success" | "failure" | "unmeasured" | string;
  taskSignature: string;
  cue: string;
  scopeJson: string;
  createdAt: string;
}

export interface EvolutionLessonOutcomes {
  lessonId: string;
  stats: EvolutionLessonStats;
  outcomes: EvolutionLessonOutcome[];
}

export interface EvolutionLessonRetireResult {
  lessonId: string;
  retired: boolean;
  stats: EvolutionLessonStats;
  reason: string;
}

export interface EvolutionSurfaceActivation {
  id: string;
  stateId: string;
  scope: string;
  snapshot: Record<string, unknown>;
  base: Record<string, unknown>;
  previousStateId: string | null;
  activatedAt: string;
  rolledBackAt: string | null;
  active?: boolean;
}

export interface EvolutionSurfaceActivationResult {
  activation: EvolutionSurfaceActivation;
}

export interface EvolutionSurfaceDiff {
  systemPromptChanged: boolean;
  systemPromptBefore: string;
  systemPromptAfter: string;
  systemPromptBeforeChars: number;
  systemPromptAfterChars: number;
  toolsAdded: string[];
  toolsRemoved: string[];
  maxStepsBefore: number;
  maxStepsAfter: number;
  maxToolCallsBefore: number;
  maxToolCallsAfter: number;
  modelIdentityChanged: boolean;
  skillDraftIds: string[];
}

export interface EvolutionDriftWindow {
  n: number;
  successes: number;
  rate: number | null;
  ciLow: number | null;
  ciHigh: number | null;
}

export interface EvolutionDriftSignal {
  status: "stable" | "drift" | "unmeasured" | string;
  scope: string;
  window: number;
  baselineWindow: number;
  current: EvolutionDriftWindow;
  baseline: EvolutionDriftWindow;
  drop: number | null;
  threshold: number;
  reasons: string[];
  availableScopes?: string[];
}

export interface EvolutionDriftHistoryPoint {
  offset: number;
  at: string | null;
  status: string;
  drop: number | null;
  current: EvolutionDriftWindow;
  baseline: EvolutionDriftWindow;
}

export interface EvolutionDriftScopeSignal {
  scope: string;
  signal: EvolutionDriftSignal;
}

export interface EvolutionDriftScopes {
  availableScopes: string[];
  signals: EvolutionDriftScopeSignal[];
}

export interface EvolutionDriftHistory {
  scope: string;
  window: number;
  baselineWindow: number;
  threshold: number;
  step: number;
  offset: number;
  requestedPoints: number;
  computedPoints: number;
  truncated: boolean;
  points: EvolutionDriftHistoryPoint[];
  availableScopes?: string[];
}

export interface EvolutionModelProposeResult {
  candidateId: string;
  children: EvolutionCandidate[];
}

export interface EvolutionDriftCandidateResult {
  created: boolean;
  reason: string;
  candidate: EvolutionCandidate | null;
  signal: EvolutionDriftSignal;
}

export interface EvolutionCandidateStateResult {
  candidateId: string;
  state: EvolutionHarnessState | null;
  states: EvolutionHarnessState[];
}

export interface EvolutionSurfaceEvidenceMetric {
  dimension: string;
  value: number | null;
  sampleSize?: number;
  scope?: string;
  category?: string;
}

export interface EvolutionSurfaceEvidenceTrial {
  taskId: string;
  trialIndex?: number;
  passed: number | boolean;
  unmeasured: number | boolean;
  status: string;
}

export interface EvolutionSurfaceTaskDelta {
  taskId: string;
  before: number | null;
  after: number | null;
  beforeN: number;
  afterN: number;
  delta: number | null;
}

export interface EvolutionSurfaceEvidence {
  run: EvolutionExperiment;
  metrics: EvolutionSurfaceEvidenceMetric[];
  trials: EvolutionSurfaceEvidenceTrial[];
  baseline: {
    run: EvolutionExperiment | null;
    metrics: EvolutionSurfaceEvidenceMetric[];
    trials: EvolutionSurfaceEvidenceTrial[];
  } | null;
  taskDeltas: EvolutionSurfaceTaskDelta[];
  criticalDeltas: EvolutionSurfaceTaskDelta[];
  target: {
    dimension: string;
    before: number | null;
    after: number | null;
    delta: number | null;
  } | null;
}

export interface EvolutionSurfacePreview {
  stateId: string;
  candidateId: string | null;
  scope: string;
  availableScopes: string[];
  referenceAgent: string;
  baseDigestMatches: boolean | null;
  accepted: boolean;
  acceptedDecision: string | null;
  canActivate: boolean;
  reasons: string[];
  diff: EvolutionSurfaceDiff | null;
  evidence: EvolutionSurfaceEvidence | null;
  previousState: EvolutionHarnessState | null;
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
  scope?: string;
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

export interface EvolutionModelExperimentInput {
  scope: string;
  provider: string;
  model: string;
  temperature?: number | null;
  dataset?: string;
  taskIds?: string[];
  split?: "optimization" | "validation" | "held_out" | "release";
  targetDimension?: string;
  trials?: number;
  seed?: number;
  problemStatement?: string;
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

export async function getEvolutionLessonOutcomes(
  lessonId: string, limit = 50,
): Promise<EvolutionLessonOutcomes> {
  return request<EvolutionLessonOutcomes>(
    `/evolution/lessons/${encodeURIComponent(lessonId)}/outcomes?limit=${encodeURIComponent(String(limit))}`,
    { method: "GET" },
  );
}

export async function retireEvolutionLesson(
  lessonId: string,
): Promise<EvolutionLessonRetireResult> {
  return request<EvolutionLessonRetireResult>(
    `/evolution/lessons/${encodeURIComponent(lessonId)}/retire`,
    { method: "POST", body: "{}" },
  );
}

export async function listEvolutionStates(
  input: { scope?: string; status?: string; limit?: number } = {},
): Promise<EvolutionHarnessStates> {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  if (input.status) params.set("status", input.status);
  params.set("limit", String(input.limit ?? 50));
  return request<EvolutionHarnessStates>(`/evolution/states?${params.toString()}`, {
    method: "GET",
  });
}

export function evolutionStatesParetoPath(
  input: { scope?: string; limit?: number } = {},
): string {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  params.set("limit", String(input.limit ?? 100));
  return `/evolution/states/pareto?${params.toString()}`;
}

export async function getEvolutionStatesPareto(
  input: { scope?: string; limit?: number } = {},
): Promise<EvolutionPareto> {
  return request<EvolutionPareto>(evolutionStatesParetoPath(input), { method: "GET" });
}

export async function promoteEvolutionState(
  stateId: string,
): Promise<{ state: EvolutionHarnessState }> {
  return request<{ state: EvolutionHarnessState }>(
    `/evolution/states/${encodeURIComponent(stateId)}/promote`,
    { method: "POST", body: "{}" },
  );
}

export async function getEvolutionCandidateState(
  candidateId: string,
  scope?: string,
): Promise<EvolutionCandidateStateResult> {
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : "";
  return request<EvolutionCandidateStateResult>(
    `/evolution/candidates/${encodeURIComponent(candidateId)}/state${query}`,
    { method: "GET" },
  );
}

export async function getEvolutionSurfacePreview(
  stateId: string,
  scope?: string,
): Promise<EvolutionSurfacePreview> {
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : "";
  return request<EvolutionSurfacePreview>(
    `/evolution/states/${encodeURIComponent(stateId)}/surface-preview${query}`,
    { method: "GET" },
  );
}

export async function activateEvolutionSurfaceState(
  stateId: string,
  scope?: string,
): Promise<EvolutionSurfaceActivationResult> {
  return request<EvolutionSurfaceActivationResult>(
    `/evolution/states/${encodeURIComponent(stateId)}/activate-surface`,
    { method: "POST", body: JSON.stringify({ scope: scope ?? null }) },
  );
}

export async function listEvolutionSurfaceActivations(
  limit = 50,
): Promise<{ activations: EvolutionSurfaceActivation[] }> {
  return request<{ activations: EvolutionSurfaceActivation[] }>(
    `/evolution/surface-activations?limit=${encodeURIComponent(String(limit))}`,
    { method: "GET" },
  );
}

export async function rollbackEvolutionSurfaceActivation(
  activationId: string,
): Promise<EvolutionSurfaceActivationResult> {
  return request<EvolutionSurfaceActivationResult>(
    `/evolution/surface-activations/${encodeURIComponent(activationId)}/rollback`,
    { method: "POST", body: "{}" },
  );
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

export async function modelProposeEvolutionCandidate(
  candidateId: string,
  k?: number,
): Promise<EvolutionModelProposeResult> {
  const query = k != null ? `?k=${encodeURIComponent(String(k))}` : "";
  return request<EvolutionModelProposeResult>(
    `/evolution/candidates/${encodeURIComponent(candidateId)}/model-propose${query}`,
    { method: "POST", body: "{}" },
  );
}

export async function getEvolutionRslStatus(): Promise<EvolutionRslStatus> {
  return request<EvolutionRslStatus>("/evolution/rsl", { method: "GET" });
}

/** The operator digest: what the loop did, what it cost, where it drifts. */
export async function getEvolutionRslReport(
  input: { days?: number; scope?: string; limit?: number } = {},
): Promise<EvolutionRslReport> {
  const params = new URLSearchParams();
  if (input.days != null) params.set("days", String(input.days));
  if (input.scope) params.set("scope", input.scope);
  if (input.limit != null) params.set("limit", String(input.limit));
  const query = params.toString();
  return request<EvolutionRslReport>(`/evolution/rsl/report${query ? `?${query}` : ""}`, {
    method: "GET",
  });
}

export async function getEvolutionDrift(
  input: { scope?: string; window?: number; baseline?: number; threshold?: number; minSamples?: number } = {},
): Promise<EvolutionDriftSignal> {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  if (input.window) params.set("window", String(input.window));
  if (input.baseline) params.set("baseline", String(input.baseline));
  if (input.threshold != null) params.set("threshold", String(input.threshold));
  if (input.minSamples != null) params.set("minSamples", String(input.minSamples));
  const query = params.toString();
  return request<EvolutionDriftSignal>(`/evolution/drift${query ? `?${query}` : ""}`, {
    method: "GET",
  });
}

export function evolutionDriftScopesPath(
  input: {
    window?: number;
    baseline?: number;
    threshold?: number;
    minSamples?: number;
    includeGlobal?: boolean;
    scopes?: string;
  } = {},
): string {
  const params = new URLSearchParams();
  if (input.window) params.set("window", String(input.window));
  if (input.baseline) params.set("baseline", String(input.baseline));
  if (input.threshold != null) params.set("threshold", String(input.threshold));
  if (input.minSamples != null) params.set("minSamples", String(input.minSamples));
  if (input.includeGlobal != null) {
    params.set("includeGlobal", input.includeGlobal ? "true" : "false");
  }
  if (input.scopes) params.set("scopes", input.scopes);
  const query = params.toString();
  return `/evolution/drift/scopes${query ? `?${query}` : ""}`;
}

export async function getEvolutionDriftScopes(
  input: {
    window?: number;
    baseline?: number;
    threshold?: number;
    minSamples?: number;
    includeGlobal?: boolean;
    scopes?: string;
  } = {},
): Promise<EvolutionDriftScopes> {
  return request<EvolutionDriftScopes>(evolutionDriftScopesPath(input), { method: "GET" });
}

export function evolutionDriftHistoryPath(
  input: {
    scope?: string;
    window?: number;
    baseline?: number;
    threshold?: number;
    minSamples?: number;
    limit?: number;
    step?: number;
    offset?: number;
  } = {},
): string {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  if (input.window) params.set("window", String(input.window));
  if (input.baseline) params.set("baseline", String(input.baseline));
  if (input.threshold != null) params.set("threshold", String(input.threshold));
  if (input.minSamples != null) params.set("minSamples", String(input.minSamples));
  if (input.limit != null) params.set("limit", String(input.limit));
  if (input.step != null) params.set("step", String(input.step));
  if (input.offset != null) params.set("offset", String(input.offset));
  const query = params.toString();
  return `/evolution/drift/history${query ? `?${query}` : ""}`;
}

export async function getEvolutionDriftHistory(
  input: {
    scope?: string;
    window?: number;
    baseline?: number;
    threshold?: number;
    minSamples?: number;
    limit?: number;
    step?: number;
    offset?: number;
  } = {},
): Promise<EvolutionDriftHistory> {
  return request<EvolutionDriftHistory>(evolutionDriftHistoryPath(input), { method: "GET" });
}

export async function createEvolutionDriftCandidate(
  input: { scope?: string; window?: number; baseline?: number; threshold?: number; minSamples?: number } = {},
): Promise<EvolutionDriftCandidateResult> {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  if (input.window) params.set("window", String(input.window));
  if (input.baseline) params.set("baseline", String(input.baseline));
  if (input.threshold != null) params.set("threshold", String(input.threshold));
  if (input.minSamples != null) params.set("minSamples", String(input.minSamples));
  const query = params.toString();
  return request<EvolutionDriftCandidateResult>(
    `/evolution/drift/candidate${query ? `?${query}` : ""}`,
    { method: "POST", body: "{}" },
  );
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

export async function createEvolutionModelExperiment(
  input: EvolutionModelExperimentInput,
): Promise<EvolutionSurfaceExperimentResult> {
  return request<EvolutionSurfaceExperimentResult>(
    "/evolution/model-experiments",
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function setEvolutionClimbPaused(
  paused: boolean,
): Promise<{ climbPaused: boolean }> {
  return request<{ climbPaused: boolean }>(
    `/evolution/rsl/climb/${paused ? "pause" : "resume"}`,
    { method: "POST", body: "{}" },
  );
}

export async function evolutionMetrics(windowDays = 90): Promise<EvolutionMetrics> {
  return request<EvolutionMetrics>(
    `/evolution/metrics?windowDays=${encodeURIComponent(String(windowDays))}`,
    { method: "GET" },
  );
}

/** The plain state key for a candidate. The ONE place a state word is chosen. */
export function evolutionStateKey(status: EvolutionStatus): string {
  return `evolution.state.${status}`;
}

/** A metric rendered as a number or the honest "not measured" value. */
export function metricLabel(value: number | "UNKNOWN"): string {
  return value === "UNKNOWN" ? "not measured yet" : String(value);
}
