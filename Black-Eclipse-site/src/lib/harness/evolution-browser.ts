// Client-side access to the RSL experiment surfaces. The Python runtime is
// reached ONLY through the Next.js /api/evolution proxy; this module never sees
// the runtime operator secret.

import type {
  EvolutionCandidateEvidence,
  EvolutionExperiment,
  EvolutionExperimentDetail,
  EvolutionLandingResult,
  EvolutionLesson,
  EvolutionLessonInput,
  EvolutionProposeInput,
  EvolutionProposeResult,
  EvolutionRecursiveResult,
  EvolutionRecursiveVariant,
  EvolutionRslStatus,
  EvolutionRslTickResult,
  EvolutionSurfaceExperimentInput,
  EvolutionSurfaceExperimentResult,
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
