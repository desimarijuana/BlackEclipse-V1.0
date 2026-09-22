// ─── Skill system browser client (Phase 3) ──────────────────────────────────
// The UI talks to the Next.js API routes (`/api/skills/**`, `/api/learning/**`),
// which proxy to the Python runtime. This module MUST stay client-safe: no
// prisma, no child_process, no fs. Fetch only.
//
// The server re-checks every mutating action (see skills-client.ts
// `isOperatorRequest`); operator controls here are a presentation hint.

import type {
  LearningCandidate,
  SkillDetail,
  SkillEvaluationRecord,
  SkillExecutionRecord,
  SkillExecutionRequest,
  SkillExecutionResult,
  SkillSummary,
} from "./skills-types";

export interface SkillListResult {
  skills: SkillSummary[];
  loadErrors: string[];
  duplicates: string[];
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new Error(body.error ?? `request failed (${res.status})`);
  return body;
}

export function clientIsOperator(): boolean {
  return typeof window !== "undefined";
}

export async function listSkills(status?: string): Promise<SkillListResult> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const body = await api<{ skills: SkillSummary[]; loadErrors?: string[]; duplicates?: string[] }>(`/api/skills${query}`);
  return { skills: body.skills ?? [], loadErrors: body.loadErrors ?? [], duplicates: body.duplicates ?? [] };
}

export async function getSkill(skillId: string): Promise<SkillDetail | null> {
  const res = await fetch(`/api/skills/${encodeURIComponent(skillId)}`);
  if (res.status === 404) return null;
  const body = (await res.json().catch(() => ({}))) as { skill?: SkillDetail; error?: string };
  if (!res.ok) throw new Error(body.error ?? "skill lookup failed");
  return body.skill ?? null;
}

export async function listCandidates(status?: string): Promise<LearningCandidate[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const body = await api<{ candidates: LearningCandidate[] }>(`/api/learning/candidates${query}`);
  return body.candidates ?? [];
}

export async function listSkillExecutions(skillId?: string): Promise<SkillExecutionRecord[]> {
  const query = skillId ? `?skillId=${encodeURIComponent(skillId)}` : "";
  const body = await api<{ executions: SkillExecutionRecord[] }>(`/api/skill-executions${query}`);
  return body.executions ?? [];
}

export async function executeSkill(req: SkillExecutionRequest): Promise<SkillExecutionResult> {
  return api<SkillExecutionResult>(`/api/skills/${encodeURIComponent(req.skillId)}/execute`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function evaluateSkill(skillId: string, version?: string, runRegression = false) {
  return api<{ success: boolean; evaluationId?: string; status: string; dimensions: SkillEvaluationRecord["dimensions"]; error?: string }>(
    `/api/skills/${encodeURIComponent(skillId)}/evaluate`,
    { method: "POST", body: JSON.stringify({ version, runRegression }) }
  );
}

export async function listSkillEvaluations(skillId: string): Promise<SkillEvaluationRecord[]> {
  const body = await api<{ evaluations: SkillEvaluationRecord[] }>(`/api/skills/${encodeURIComponent(skillId)}/evaluations`);
  return body.evaluations ?? [];
}

export async function generateDraft(candidateId: string) {
  return api<{ ok: boolean; draft?: Record<string, unknown>; issues?: string[]; error?: string }>(
    `/api/learning/candidates/${encodeURIComponent(candidateId)}/generate-draft`,
    { method: "POST", body: JSON.stringify({}) }
  );
}

export async function rejectCandidate(candidateId: string) {
  return api<{ ok: boolean; error?: string }>(
    `/api/learning/candidates/${encodeURIComponent(candidateId)}/reject`,
    { method: "POST", body: JSON.stringify({}) }
  );
}

export async function learnFromRun(runId: string) {
  return api<{ ok: boolean; created: LearningCandidate[]; duplicates: string[]; error?: string }>(
    `/api/learning/from-run/${encodeURIComponent(runId)}`,
    { method: "POST", body: JSON.stringify({}) }
  );
}

export async function setSkillLifecycle(skillId: string, action: "enable" | "disable" | "deprecate" | "rollback", payload: Record<string, unknown> = {}) {
  return api<{ success?: boolean; error?: string; status?: string }>(
    `/api/skills/${encodeURIComponent(skillId)}/${action}`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export interface AuthoringMeta {
  tools: string[];
  permissions: string[];
  categories: string[];
  riskLevels: string[];
}

export async function getAuthoringMeta(): Promise<AuthoringMeta> {
  return api<AuthoringMeta>("/api/skills/authoring/tools");
}

export interface AuthorSkillInput {
  name: string;
  description: string;
  instructions: string;
  category?: string;
  tags?: string[];
  requiredTools?: string[];
  permissions?: string[];
  riskLevel?: string;
  skillId?: string;
}

export async function createUserSkill(payload: AuthorSkillInput) {
  return api<{ success: boolean; skillId: string; version: string; status: string }>("/api/skills/author", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateUserSkill(skillId: string, patch: Partial<AuthorSkillInput>) {
  return api<{ success: boolean; skillId: string; version: string; status: string }>(
    `/api/skills/${encodeURIComponent(skillId)}/author`,
    { method: "PUT", body: JSON.stringify(patch) }
  );
}

export async function deleteUserSkill(skillId: string) {
  return api<{ success: boolean; skillId: string; deleted: boolean; status?: string; reason?: string }>(
    `/api/skills/${encodeURIComponent(skillId)}/author`,
    { method: "DELETE", body: JSON.stringify({}) }
  );
}

export async function submitDraftReview(skillId: string, reason: string, evaluationId?: string) {
  return api<{ success?: boolean; error?: string; requestId?: string }>(
    `/api/skill-drafts/${encodeURIComponent(skillId)}/submit-review`,
    { method: "POST", body: JSON.stringify({ reason, evaluationId }) }
  );
}

export async function approveDraft(skillId: string, requestId: string, notes = "") {
  return api<{ success?: boolean; error?: string; status?: string }>(
    `/api/skill-drafts/${encodeURIComponent(skillId)}/approve`,
    { method: "POST", body: JSON.stringify({ requestId, notes }) }
  );
}

export async function rejectDraft(skillId: string, requestId: string, reason: string) {
  return api<{ success?: boolean; error?: string }>(
    `/api/skill-drafts/${encodeURIComponent(skillId)}/reject`,
    { method: "POST", body: JSON.stringify({ requestId, reason }) }
  );
}
