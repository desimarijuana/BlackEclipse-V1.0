// â”€â”€â”€ Skill system browser client (Phase 3) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// The UI talks to the Next.js API routes (`/api/skills/**`, `/api/learning/**`),
// which proxy to the Python runtime. This module MUST stay client-safe: no
// prisma, no child_process, no fs. Fetch only.
//
// The server re-checks every mutating action (see skills-client.ts
// `isOperatorRequest`); operator controls here are a presentation hint.

import type {
  LearnDraftResult,
  LearnRequest,
  LearningCandidate,
  LearningJourney,
  OnboardingContent,
  ProjectSkillStatus,
  SkillBundle,
  SkillBundleListResponse,
  SkillBundleResolution,
  SkillContentScan,
  SkillDetail,
  SkillPromotionEvidence,
  SkillQualityComparison,
  SkillQualityMetrics,
  SkillEvaluationRecord,
  SkillExecutionRecord,
  SkillExecutionRequest,
  SkillExecutionResult,
  SkillPatchOperation,
  SkillPatchResult,
  SkillSummary,
  SkillVersionHistoryEntry,
} from "./skills-types";

export interface SkillListResult {
  skills: SkillSummary[];
  loadErrors: string[];
  duplicates: string[];
  projectNotices: string[];
  projectDrift: boolean;
  shadowed: string[];
  contentFindings: Record<string, SkillContentScan>;
  quarantined: string[];
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
  const body = await api<{
    skills: SkillSummary[]; loadErrors?: string[]; duplicates?: string[];
    projectNotices?: string[]; projectDrift?: boolean; shadowed?: string[];
    contentFindings?: Record<string, SkillContentScan>; quarantined?: string[];
  }>(`/api/skills${query}`);
  return {
    skills: body.skills ?? [],
    loadErrors: body.loadErrors ?? [],
    duplicates: body.duplicates ?? [],
    projectNotices: body.projectNotices ?? [],
    projectDrift: body.projectDrift ?? false,
    shadowed: body.shadowed ?? [],
    contentFindings: body.contentFindings ?? {},
    quarantined: body.quarantined ?? [],
  };
}

export async function projectSkillStatus(): Promise<ProjectSkillStatus> {
  return api<ProjectSkillStatus>(`/api/skills/project`);
}

export async function trustProjectSkill(path?: string, note?: string): Promise<void> {
  await api(`/api/skills/project/trust`, { method: "POST", body: JSON.stringify({ path, note }) });
}

export async function approveProjectSkill(path?: string, note?: string): Promise<void> {
  await api(`/api/skills/project/approve`, { method: "POST", body: JSON.stringify({ path, note }) });
}

export async function untrustProjectSkill(path?: string): Promise<void> {
  await api(`/api/skills/project/untrust`, { method: "POST", body: JSON.stringify({ path }) });
}

export async function getSkillQuality(skillId: string, version?: string): Promise<SkillQualityMetrics> {
  const query = version ? `?version=${encodeURIComponent(version)}` : "";
  return api<SkillQualityMetrics>(`/api/skills/${encodeURIComponent(skillId)}/quality${query}`);
}

export async function getSkillPromotionEvidence(skillId: string, version: string): Promise<SkillPromotionEvidence> {
  return api<SkillPromotionEvidence>(`/api/skills/${encodeURIComponent(skillId)}/promotion-evidence?version=${encodeURIComponent(version)}`);
}

export async function compareSkillVersions(skillId: string, older: string, newer: string): Promise<SkillQualityComparison> {
  const query = new URLSearchParams({ older, newer }).toString();
  return api<SkillQualityComparison>(`/api/skills/${encodeURIComponent(skillId)}/quality/compare?${query}`);
}

export async function learningJourney(params: { kind?: string; status?: string; since?: string } = {}): Promise<LearningJourney> {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v) as [string, string][]
  ).toString();
  return api<LearningJourney>(`/api/learning/journey${query ? `?${query}` : ""}`);
}

export async function learnFromSource(request: LearnRequest): Promise<LearnDraftResult> {
  return api<LearnDraftResult>(`/api/learning/from-source`, { method: "POST", body: JSON.stringify(request) });
}

export async function getSkillPreflight(skillId: string): Promise<{
  skillId: string; ok: boolean; reasons: string[];
  validation: unknown; dependencyGraph: unknown;
}> {
  return api(`/api/skills/${encodeURIComponent(skillId)}/preflight`);
}

export async function getOnboarding(): Promise<OnboardingContent> {
  return api<OnboardingContent>(`/api/onboarding`);
}

export async function listSkillBundles(): Promise<SkillBundleListResponse> {
  const body = await api<{ bundles?: SkillBundle[]; resolved?: Record<string, SkillBundleResolution> }>(`/api/skill-bundles`);
  return { bundles: body.bundles ?? [], resolved: body.resolved ?? {} };
}

export async function saveSkillBundle(bundle: Partial<SkillBundle> & { id: string }): Promise<SkillBundle> {
  const body = await api<{ bundle: SkillBundle }>(`/api/skill-bundles`, { method: "POST", body: JSON.stringify(bundle) });
  return body.bundle;
}

export async function lockSkillBundle(bundleId: string): Promise<{ ok: boolean }> {
  return api(`/api/skill-bundles/${encodeURIComponent(bundleId)}/lock`, { method: "POST" });
}

export async function unlockSkillBundle(bundleId: string): Promise<{ ok: boolean }> {
  return api(`/api/skill-bundles/${encodeURIComponent(bundleId)}/lock`, { method: "DELETE" });
}

export async function deleteSkillBundle(bundleId: string): Promise<void> {
  await api(`/api/skill-bundles/${encodeURIComponent(bundleId)}`, { method: "DELETE" });
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

export async function generateDraft(candidateId: string, userIntent?: string) {
  return api<{ ok: boolean; draft?: Record<string, unknown>; issues?: string[]; reusable?: boolean; error?: string }>(
    `/api/learning/candidates/${encodeURIComponent(candidateId)}/generate-draft`,
    { method: "POST", body: JSON.stringify({ userIntent }) }
  );
}

export async function rejectCandidate(candidateId: string) {
  return api<{ ok: boolean; error?: string }>(
    `/api/learning/candidates/${encodeURIComponent(candidateId)}/reject`,
    { method: "POST", body: JSON.stringify({}) }
  );
}

export async function learnFromRun(runId: string, userIntent?: string) {
  return api<{ ok: boolean; created: LearningCandidate[]; duplicates: string[]; error?: string }>(
    `/api/learning/from-run/${encodeURIComponent(runId)}`,
    { method: "POST", body: JSON.stringify({ userIntent }) }
  );
}

export async function setSkillLifecycle(skillId: string, action: "enable" | "disable" | "deprecate" | "rollback", payload: Record<string, unknown> = {}) {
  return api<{ success?: boolean; error?: string; status?: string }>(
    `/api/skills/${encodeURIComponent(skillId)}/${action}`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

// â”€â”€ Versioned patches (M2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export async function getSkillVersionHistory(skillId: string): Promise<{ success: boolean; skillId: string; versions: SkillVersionHistoryEntry[] }> {
  return api(`/api/skills/${encodeURIComponent(skillId)}/version-history`);
}

export async function proposeSkillPatch(
  skillId: string, baseVersion: string, operations: SkillPatchOperation[],
  extra: { reason?: string; author?: string; reviewId?: string; sourceRunId?: string } = {},
) {
  return api<SkillPatchResult>(`/api/skills/${encodeURIComponent(skillId)}/patch`, {
    method: "POST",
    body: JSON.stringify({ baseVersion, operations, ...extra }),
  });
}

export async function skillVersionAction(
  skillId: string, version: string,
  action: "evaluate" | "activate" | "promote" | "auto-rollback-check",
  payload: Record<string, unknown> = {},
) {
  return api<{ success?: boolean; error?: string; [k: string]: unknown }>(
    `/api/skills/${encodeURIComponent(skillId)}/patch/${encodeURIComponent(version)}/${action}`,
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

