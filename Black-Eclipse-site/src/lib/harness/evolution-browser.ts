// Client-side access to the RSL experiment surfaces. The Python runtime is
// reached ONLY through the Next.js /api/evolution proxy; this module never sees
// the runtime operator secret.

import type {
  EvolutionCandidateEvidence,
  EvolutionCandidateStateResult,
  EvolutionDriftCandidateResult,
  EvolutionDriftHistory,
  EvolutionDriftScopes,
  EvolutionDriftSignal,
  EvolutionExperiment,
  EvolutionExperimentDetail,
  EvolutionLandingResult,
  EvolutionHarnessState,
  EvolutionHarnessStates,
  EvolutionLesson,
  EvolutionLessonInput,
  EvolutionLessonOutcomes,
  EvolutionLessonRetireResult,
  EvolutionMetrics,
  EvolutionModelExperimentInput,
  EvolutionPareto,
  EvolutionModelProposeResult,
  EvolutionProposeInput,
  EvolutionProposeResult,
  EvolutionRecursiveResult,
  EvolutionRecursiveVariant,
  EvolutionRslStatus,
  EvolutionRslTickResult,
  EvolutionSurfaceActivation,
  EvolutionSurfaceActivationResult,
  EvolutionSurfaceExperimentInput,
  EvolutionSurfaceExperimentResult,
  EvolutionSurfacePreview,
} from "./evolution-client";

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    cache: "no-store",
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(
      (body as { error?: string }).error || `request failed (${res.status})`,
    );
  }
  return body as T;
}

export async function getEvolutionMetricsBrowser(
  windowDays = 90,
): Promise<EvolutionMetrics> {
  return api<EvolutionMetrics>(
    `/api/evolution/metrics?windowDays=${encodeURIComponent(String(windowDays))}`,
  );
}

export async function listEvolutionExperimentsBrowser(limit = 50): Promise<EvolutionExperiment[]> {
  const body = await api<{ experiments: EvolutionExperiment[] }>(
    `/api/evolution/experiments?limit=${encodeURIComponent(String(limit))}`,
  );
  return body.experiments ?? [];
}

export async function getEvolutionExperimentBrowser(id: string): Promise<EvolutionExperimentDetail> {
  return api<EvolutionExperimentDetail>(
    `/api/evolution/experiments/${encodeURIComponent(id)}`,
  );
}

export async function evolutionCandidateEvidenceBrowser(id: string): Promise<EvolutionCandidateEvidence> {
  return api<EvolutionCandidateEvidence>(
    `/api/evolution/candidates/${encodeURIComponent(id)}/evidence`,
  );
}

export async function getEvolutionCandidateStateBrowser(
  id: string,
  scope?: string,
): Promise<EvolutionCandidateStateResult> {
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : "";
  return api<EvolutionCandidateStateResult>(
    `/api/evolution/candidates/${encodeURIComponent(id)}/state${query}`,
  );
}

export async function prepareEvolutionLandingBrowser(id: string): Promise<EvolutionLandingResult> {
  return api<EvolutionLandingResult>(
    `/api/evolution/candidates/${encodeURIComponent(id)}/prepare-landing`,
    { method: "POST", body: "{}" },
  );
}

export async function listEvolutionLessonsBrowser(limit = 50): Promise<EvolutionLesson[]> {
  const body = await api<{ lessons: EvolutionLesson[] }>(
    `/api/evolution/lessons?limit=${encodeURIComponent(String(limit))}`,
  );
  return body.lessons ?? [];
}

export async function getEvolutionLessonOutcomesBrowser(
  lessonId: string, limit = 50,
): Promise<EvolutionLessonOutcomes> {
  return api<EvolutionLessonOutcomes>(
    `/api/evolution/lessons/${encodeURIComponent(lessonId)}/outcomes?limit=${encodeURIComponent(String(limit))}`,
  );
}

export async function retireEvolutionLessonBrowser(
  lessonId: string,
): Promise<EvolutionLessonRetireResult> {
  return api<EvolutionLessonRetireResult>(
    `/api/evolution/lessons/${encodeURIComponent(lessonId)}/retire`,
    { method: "POST", body: "{}" },
  );
}

export async function listEvolutionStatesBrowser(
  input: { scope?: string; status?: string; limit?: number } = {},
): Promise<EvolutionHarnessStates> {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  if (input.status) params.set("status", input.status);
  params.set("limit", String(input.limit ?? 50));
  return api<EvolutionHarnessStates>(`/api/evolution/states?${params.toString()}`);
}

export async function getEvolutionStatesParetoBrowser(
  input: { scope?: string; limit?: number } = {},
): Promise<EvolutionPareto> {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  params.set("limit", String(input.limit ?? 100));
  return api<EvolutionPareto>(`/api/evolution/states/pareto?${params.toString()}`);
}

export async function promoteEvolutionStateBrowser(
  stateId: string,
): Promise<{ state: EvolutionHarnessState }> {
  return api<{ state: EvolutionHarnessState }>(
    `/api/evolution/states/${encodeURIComponent(stateId)}/promote`,
    { method: "POST", body: "{}" },
  );
}

export async function getEvolutionSurfacePreviewBrowser(
  stateId: string,
  scope?: string,
): Promise<EvolutionSurfacePreview> {
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : "";
  return api<EvolutionSurfacePreview>(
    `/api/evolution/states/${encodeURIComponent(stateId)}/surface-preview${query}`,
  );
}

export async function activateEvolutionSurfaceStateBrowser(
  stateId: string,
  scope?: string,
): Promise<EvolutionSurfaceActivationResult> {
  return api<EvolutionSurfaceActivationResult>(
    `/api/evolution/states/${encodeURIComponent(stateId)}/activate-surface`,
    { method: "POST", body: JSON.stringify({ scope: scope ?? null }) },
  );
}

export async function listEvolutionSurfaceActivationsBrowser(
  limit = 50,
): Promise<EvolutionSurfaceActivation[]> {
  const body = await api<{ activations: EvolutionSurfaceActivation[] }>(
    `/api/evolution/surface-activations?limit=${encodeURIComponent(String(limit))}`,
  );
  return body.activations ?? [];
}

export async function rollbackEvolutionSurfaceActivationBrowser(
  activationId: string,
): Promise<EvolutionSurfaceActivationResult> {
  return api<EvolutionSurfaceActivationResult>(
    `/api/evolution/surface-activations/${encodeURIComponent(activationId)}/rollback`,
    { method: "POST", body: "{}" },
  );
}

export async function adoptEvolutionLessonBrowser(
  candidateId: string, input: EvolutionLessonInput,
): Promise<{ stored: boolean; duplicate?: boolean; lesson: EvolutionLesson }> {
  return api(
    `/api/evolution/candidates/${encodeURIComponent(candidateId)}/lessons`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function runEvolutionRecursiveBrowser(
  candidateId: string,
  input: { variants: EvolutionRecursiveVariant[]; seed?: number },
): Promise<EvolutionRecursiveResult> {
  return api<EvolutionRecursiveResult>(
    `/api/evolution/candidates/${encodeURIComponent(candidateId)}/recursive`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function createEvolutionSurfaceExperimentBrowser(
  input: EvolutionSurfaceExperimentInput,
): Promise<EvolutionSurfaceExperimentResult> {
  return api<EvolutionSurfaceExperimentResult>(
    "/api/evolution/surface-experiments",
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function getEvolutionRslStatusBrowser(): Promise<EvolutionRslStatus> {
  return api<EvolutionRslStatus>("/api/evolution/rsl");
}

export async function getEvolutionDriftBrowser(
  input: {
    scope?: string;
    window?: number;
    baseline?: number;
    threshold?: number;
    minSamples?: number;
  } = {},
): Promise<EvolutionDriftSignal> {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  if (input.window) params.set("window", String(input.window));
  if (input.baseline) params.set("baseline", String(input.baseline));
  if (input.threshold != null) params.set("threshold", String(input.threshold));
  if (input.minSamples != null) params.set("minSamples", String(input.minSamples));
  const query = params.toString();
  return api<EvolutionDriftSignal>(`/api/evolution/drift${query ? `?${query}` : ""}`);
}

export async function getEvolutionDriftScopesBrowser(
  input: {
    window?: number;
    baseline?: number;
    threshold?: number;
    minSamples?: number;
    includeGlobal?: boolean;
    scopes?: string;
  } = {},
): Promise<EvolutionDriftScopes> {
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
  return api<EvolutionDriftScopes>(
    `/api/evolution/drift/scopes${query ? `?${query}` : ""}`,
  );
}

export async function getEvolutionDriftHistoryBrowser(
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
  return api<EvolutionDriftHistory>(
    `/api/evolution/drift/history${query ? `?${query}` : ""}`,
  );
}

export async function createEvolutionDriftCandidateBrowser(
  input: {
    scope?: string;
    window?: number;
    baseline?: number;
    threshold?: number;
    minSamples?: number;
  } = {},
): Promise<EvolutionDriftCandidateResult> {
  const params = new URLSearchParams();
  if (input.scope) params.set("scope", input.scope);
  if (input.window) params.set("window", String(input.window));
  if (input.baseline) params.set("baseline", String(input.baseline));
  if (input.threshold != null) params.set("threshold", String(input.threshold));
  if (input.minSamples != null) params.set("minSamples", String(input.minSamples));
  const query = params.toString();
  return api<EvolutionDriftCandidateResult>(
    `/api/evolution/drift/candidate${query ? `?${query}` : ""}`,
    { method: "POST", body: "{}" },
  );
}

export async function createEvolutionModelExperimentBrowser(
  input: EvolutionModelExperimentInput,
): Promise<EvolutionSurfaceExperimentResult> {
  return api<EvolutionSurfaceExperimentResult>(
    "/api/evolution/model-experiments",
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function setEvolutionClimbPausedBrowser(
  paused: boolean,
): Promise<{ climbPaused: boolean }> {
  return api<{ climbPaused: boolean }>(
    `/api/evolution/rsl/climb/${paused ? "pause" : "resume"}`,
    { method: "POST", body: "{}" },
  );
}

export async function tickEvolutionRslBrowser(): Promise<EvolutionRslTickResult> {
  return api<EvolutionRslTickResult>("/api/evolution/rsl/tick", {
    method: "POST", body: "{}",
  });
}

export async function proposeEvolutionCandidateBrowser(
  candidateId: string, input: EvolutionProposeInput,
): Promise<EvolutionProposeResult> {
  return api<EvolutionProposeResult>(
    `/api/evolution/candidates/${encodeURIComponent(candidateId)}/propose`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function modelProposeEvolutionCandidateBrowser(
  candidateId: string,
  k?: number,
): Promise<EvolutionModelProposeResult> {
  const query = k != null ? `?k=${encodeURIComponent(String(k))}` : "";
  return api<EvolutionModelProposeResult>(
    `/api/evolution/candidates/${encodeURIComponent(candidateId)}/model-propose${query}`,
    { method: "POST", body: "{}" },
  );
}
