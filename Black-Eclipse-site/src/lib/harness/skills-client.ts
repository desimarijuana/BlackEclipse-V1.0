// â”€â”€â”€ Skill system front door (Phase 3) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Thin typed wrapper over the Python runtime's /skills, /learning and /evaluation
// endpoints. It adds no skill logic â€” it resolves the model settings the runtime
// cannot (from the vault) and forwards. There is exactly one skill registry, in
// Python.

import { getLLMConfig } from "@/lib/settings";
import { checkMutationAllowed } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeBaseUrl, runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets, HarnessHttpError, isNotFoundError } from "./errors";
import type {
  LearnDraftResult,
  LearnRequest,
  LearningCandidate,
  LearningJourney,
  OnboardingContent,
  ProjectSkillStatus,
  ProjectTrustApproval,
  SkillBundle,
  SkillBundleListResponse,
  SkillBundleResolution,
  BundleUpdatePreview,
  SkillDetail,
  SkillPromotionEvidence,
  SkillQualityComparison,
  SkillQualityMetrics,
  SkillEvaluationRecord,
  SkillExecutionRecord,
  SkillExecutionRequest,
  SkillExecutionResult,
  SkillListResponse,
  SkillPatchOperation,
  SkillSummary,
  SkillVersionHistoryEntry,
  SkillMaintenanceReport,
  SkillMaintenanceRunResult,
} from "./skills-types";

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python"
    );
  }
  const { timeoutMs = 60_000, ...rest } = init;
  // The Python runtime authorizes operator mutations by transport (loopback) or
  // by this secret â€” never by a body boolean. Forwarding it means the front
  // door's own authorization is what reaches Python, even if the runtime is
  // later bound to a non-loopback interface. The value is never logged.
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
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new HarnessHttpError(res.status, redactSecrets(detail), detail);
  }
  return body as T;
}

/**
 * Whether this request is an authorized operator.
 *
 * Operator actions (create/evaluate/enable/disable/review) are gated exactly
 * like every other mutation in this repo: `checkMutationAllowed` â€” a same-origin
 * browser request OR a caller presenting the runtime secret OR a request to a
 * loopback host. This keeps the zero-config local install fully usable while a
 * public deployment still requires CRON_SECRET.
 *
 * The Python runtime re-enforces its own default-deny permission policy, so this
 * is defense in depth, not the only gate. Skill *instructions* are never a
 * boundary â€” the permission check runs in code on the composed AgentConfig.
 */
export function isOperatorRequest(request?: Request): boolean {
  if (!request) return false;
  return checkMutationAllowed(request).allowed;
}

export async function listSkills(status?: string): Promise<SkillListResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const body = await request<SkillListResponse>(
    `/skills${query}`,
    { method: "GET" }
  );
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
  return request<ProjectSkillStatus & { success: true }>("/skills/project", { method: "GET" });
}

export async function trustProjectSkill(path?: string, note?: string): Promise<void> {
  await request(`/skills/project/trust`, {
    method: "POST",
    body: JSON.stringify({ path, note }),
  });
}

export async function approveProjectSkill(path?: string, note?: string, skillIds?: string[]): Promise<void> {
  await request(`/skills/project/approve`, {
    method: "POST",
    body: JSON.stringify({ path, note, skillIds }),
  });
}

export async function untrustProjectSkill(path?: string): Promise<void> {
  await request(`/skills/project/untrust`, {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export async function projectTrustHistory(path?: string): Promise<ProjectTrustApproval[]> {
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  const body = await request<{ success: true; history: ProjectTrustApproval[] }>(
    `/skills/project/history${query}`,
    { method: "GET" }
  );
  return body.history ?? [];
}

export async function learningJourney(params: { kind?: string; status?: string; since?: string } = {}): Promise<LearningJourney> {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v) as [string, string][]
  ).toString();
  return request<LearningJourney & { success: true }>(`/learning/journey${query ? `?${query}` : ""}`, { method: "GET" });
}

export async function getSkillQuality(skillId: string, version?: string): Promise<SkillQualityMetrics> {
  const query = version ? `?version=${encodeURIComponent(version)}` : "";
  return request<SkillQualityMetrics & { success: true }>(
    `/skills/${encodeURIComponent(skillId)}/quality${query}`, { method: "GET" }
  );
}

export async function getSkillPromotionEvidence(skillId: string, version: string): Promise<SkillPromotionEvidence> {
  return request<SkillPromotionEvidence & { success: true }>(
    `/skills/${encodeURIComponent(skillId)}/promotion-evidence?version=${encodeURIComponent(version)}`, { method: "GET" }
  );
}

export async function compareSkillVersions(skillId: string, older: string, newer: string): Promise<SkillQualityComparison> {
  const query = new URLSearchParams({ older, newer }).toString();
  return request<SkillQualityComparison & { success: true }>(
    `/skills/${encodeURIComponent(skillId)}/quality/compare?${query}`, { method: "GET" }
  );
}

export async function learnFromSource(learnRequest: LearnRequest): Promise<LearnDraftResult> {
  return request<LearnDraftResult>("/learning/from-source", {
    method: "POST",
    body: JSON.stringify({ ...learnRequest, operator: true }),
  });
}

export async function getSkillPreflight(skillId: string): Promise<{
  skillId: string; ok: boolean; reasons: string[];
  validation: unknown; dependencyGraph: unknown;
}> {
  return request(`/skills/${encodeURIComponent(skillId)}/preflight`, { method: "GET" });
}

export async function getOnboarding(): Promise<OnboardingContent> {
  return request<OnboardingContent & { success: true }>("/onboarding", { method: "GET" });
}

export async function getSkillMaintenance(): Promise<SkillMaintenanceReport> {
  return request<SkillMaintenanceReport & { success: true }>("/skills/maintenance", { method: "GET" });
}

export async function runSkillMaintenance(): Promise<SkillMaintenanceRunResult> {
  return request<SkillMaintenanceRunResult & { success: true }>("/skills/maintenance/run", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function pinSkillVersion(
  skillId: string, version: string | undefined, pinned: boolean,
): Promise<{ success: true; pinned: boolean }> {
  return request(`/skills/${encodeURIComponent(skillId)}/pin`, {
    method: "POST",
    body: JSON.stringify({ version, pinned }),
  });
}

export async function listSkillBundles(): Promise<SkillBundleListResponse> {
  const body = await request<{ bundles?: SkillBundle[]; resolved?: Record<string, SkillBundleResolution> }>(
    "/skill-bundles",
    { method: "GET" }
  );
  return { bundles: body.bundles ?? [], resolved: body.resolved ?? {} };
}

export async function saveSkillBundle(bundle: Partial<SkillBundle> & { id: string }): Promise<SkillBundle> {
  const body = await request<{ bundle: SkillBundle }>("/skill-bundles", {
    method: "POST",
    body: JSON.stringify(bundle),
  });
  return body.bundle;
}

export async function lockSkillBundle(bundleId: string): Promise<{ ok: boolean }> {
  return request(`/skill-bundles/${encodeURIComponent(bundleId)}/lock`, { method: "POST" });
}

export async function unlockSkillBundle(bundleId: string): Promise<{ ok: boolean }> {
  return request(`/skill-bundles/${encodeURIComponent(bundleId)}/lock`, { method: "DELETE" });
}

export async function bundleUpdatePreview(bundleId: string): Promise<BundleUpdatePreview> {
  return request(`/skill-bundles/${encodeURIComponent(bundleId)}/update-preview`, { method: "GET" });
}

export async function rollbackSkillBundle(bundleId: string): Promise<{ ok: boolean }> {
  return request(`/skill-bundles/${encodeURIComponent(bundleId)}/rollback`, { method: "POST" });
}

export async function deleteSkillBundle(bundleId: string): Promise<void> {
  await request(`/skill-bundles/${encodeURIComponent(bundleId)}`, { method: "DELETE" });
}

export async function getSkill(skillId: string): Promise<SkillDetail | null> {
  try {
    const body = await request<{ skill: SkillDetail }>(`/skills/${encodeURIComponent(skillId)}`, { method: "GET" });
    return body.skill;
  } catch (err) {
    if (isNotFoundError(err)) return null;
    throw err;
  }
}

export async function discoverSkills(params: {
  query?: string;
  category?: string;
  tags?: string[];
  status?: string;
  riskLevel?: string;
  includeNonExecutable?: boolean;
}): Promise<SkillSummary[]> {
  const body = await request<{ results: SkillSummary[] }>("/skills/discover", {
    method: "POST",
    body: JSON.stringify(params),
  });
  return body.results ?? [];
}

export async function validateSkillInput(
  skillId: string,
  input: Record<string, unknown>
): Promise<{ valid: boolean; issues: string[] }> {
  const body = await request<{ valid: boolean; issues: string[] }>("/skills/validate-input", {
    method: "POST",
    body: JSON.stringify({ skillId, input }),
  });
  return { valid: body.valid, issues: body.issues ?? [] };
}

/** Resolve model settings exactly as a chat run does. */
async function resolveModelSettings() {
  const cfg = await getLLMConfig();
  const provider = cfg.provider === "auto" || cfg.provider === "mock" ? "openai" : cfg.provider;
  return { provider, baseUrl: cfg.baseUrl, apiKey: cfg.apiKey, model: cfg.model };
}

/**
 * Execute a skill through the existing runtime using the stable, workflow-ready
 * contract. The model settings + callback info are injected here, the same way
 * a chat run gets them.
 */
export async function executeSkill(
  req: SkillExecutionRequest,
  opts: { operator?: boolean } = {}
): Promise<SkillExecutionResult> {
  const modelSettings = await resolveModelSettings();
  const body = await request<SkillExecutionResult & { success: boolean }>(
    `/skills/${encodeURIComponent(req.skillId)}/execute`,
    {
      method: "POST",
      timeoutMs: 240_000,
      body: JSON.stringify({
        ...req,
        operator: opts.operator ?? false,
        modelSettings,
        callbackBaseUrl: runtimeBaseUrl(),
        callbackToken: runtimeCallbackToken(),
      }),
    }
  );
  return body;
}

export async function listSkillExecutions(skillId?: string): Promise<SkillExecutionRecord[]> {
  const query = skillId ? `?skillId=${encodeURIComponent(skillId)}` : "";
  const body = await request<{ executions: SkillExecutionRecord[] }>(`/skill-executions${query}`, { method: "GET" });
  return body.executions ?? [];
}

export async function getSkillExecution(runId: string): Promise<SkillExecutionRecord | null> {
  try {
    const body = await request<{ execution: SkillExecutionRecord }>(
      `/skill-executions/${encodeURIComponent(runId)}`,
      { method: "GET" }
    );
    return body.execution;
  } catch (err) {
    if (isNotFoundError(err)) return null;
    throw err;
  }
}

export async function cancelSkillExecution(runId: string): Promise<boolean> {
  const body = await request<{ cancelled: boolean }>(
    `/skill-executions/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" }
  );
  return Boolean(body.cancelled);
}

export async function evaluateSkill(
  skillId: string,
  version?: string,
  runRegression = false
): Promise<{ ok: boolean; evaluationId?: string; status: string; dimensions: SkillEvaluationRecord["dimensions"]; error?: string }> {
  return request(`/skills/${encodeURIComponent(skillId)}/evaluate`, {
    method: "POST",
    timeoutMs: 120_000,
    body: JSON.stringify({ version, runRegression }),
  });
}

export async function listSkillEvaluations(skillId: string): Promise<SkillEvaluationRecord[]> {
  const body = await request<{ evaluations: SkillEvaluationRecord[] }>(
    `/skills/${encodeURIComponent(skillId)}/evaluations`,
    { method: "GET" }
  );
  return body.evaluations ?? [];
}

export async function getEvaluation(evaluationId: string): Promise<SkillEvaluationRecord | null> {
  try {
    const body = await request<{ evaluation: SkillEvaluationRecord }>(
      `/evaluations/${encodeURIComponent(evaluationId)}`,
      { method: "GET" }
    );
    return body.evaluation;
  } catch (err) {
    if (isNotFoundError(err)) return null;
    throw err;
  }
}

export async function listCandidates(status?: string): Promise<LearningCandidate[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const body = await request<{ candidates: LearningCandidate[] }>(`/learning/candidates${query}`, { method: "GET" });
  return body.candidates ?? [];
}

export async function getCandidate(candidateId: string): Promise<LearningCandidate | null> {
  try {
    const body = await request<{ candidate: LearningCandidate }>(
      `/learning/candidates/${encodeURIComponent(candidateId)}`,
      { method: "GET" }
    );
    return body.candidate;
  } catch (err) {
    if (isNotFoundError(err)) return null;
    throw err;
  }
}

export async function learnFromRun(runId: string, operator: boolean, userIntent?: string): Promise<{ ok: boolean; created: LearningCandidate[]; duplicates: string[]; error?: string }> {
  return request(`/learning/from-run/${encodeURIComponent(runId)}`, {
    method: "POST",
    body: JSON.stringify({ operator, userIntent }),
  });
}

export interface LearningEligibility {
  runId: string;
  eligible: boolean;
  reason: string;
  modelSteps: number;
  toolCalls: number;
  skillRequested: boolean;
  learnQueuePath: string;
}

export async function getLearningEligibility(runId: string): Promise<LearningEligibility> {
  return request(`/learning/eligibility/${encodeURIComponent(runId)}`, { method: "GET" });
}

export async function generateDraft(candidateId: string, operator: boolean, userIntent?: string): Promise<{ ok: boolean; draft?: Record<string, unknown>; issues?: string[]; reusable?: boolean; error?: string }> {
  return request(`/learning/candidates/${encodeURIComponent(candidateId)}/generate-draft`, {
    method: "POST",
    body: JSON.stringify({ operator, userIntent }),
  });
}

export async function rejectCandidate(candidateId: string, operator: boolean): Promise<{ ok: boolean; error?: string }> {
  return request(`/learning/candidates/${encodeURIComponent(candidateId)}/reject`, {
    method: "POST",
    body: JSON.stringify({ operator }),
  });
}

export async function enableSkill(skillId: string, operator: boolean, version?: string) {
  return request(`/skills/${encodeURIComponent(skillId)}/enable`, {
    method: "POST",
    body: JSON.stringify({ operator, version }),
  });
}

export async function disableSkill(skillId: string, operator: boolean, version?: string) {
  return request(`/skills/${encodeURIComponent(skillId)}/disable`, {
    method: "POST",
    body: JSON.stringify({ operator, version }),
  });
}

export async function deprecateSkill(skillId: string, operator: boolean, reason: string, supersededBy?: string) {
  return request(`/skills/${encodeURIComponent(skillId)}/deprecate`, {
    method: "POST",
    body: JSON.stringify({ operator, reason, supersededBy }),
  });
}

export async function rollbackSkill(skillId: string, operator: boolean, version: string, reason: string) {
  return request(`/skills/${encodeURIComponent(skillId)}/rollback`, {
    method: "POST",
    body: JSON.stringify({ operator, version, reason }),
  });
}

// â”€â”€ Versioned skill patches (M2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export async function getSkillVersionHistory(skillId: string): Promise<{ success: boolean; skillId: string; versions: SkillVersionHistoryEntry[] }> {
  return request(`/skills/${encodeURIComponent(skillId)}/version-history`, { method: "GET" });
}

export async function proposeSkillPatch(
  skillId: string,
  payload: { baseVersion: string; operations: SkillPatchOperation[]; reason?: string; author?: string; reviewId?: string; sourceRunId?: string; operator: boolean },
) {
  return request(`/skills/${encodeURIComponent(skillId)}/patch`, {
    method: "POST",
    body: JSON.stringify({ skill: skillId, ...payload }),
  });
}

export async function evaluateSkillVersion(skillId: string, version: string, operator: boolean) {
  return request(`/skills/${encodeURIComponent(skillId)}/patch/${encodeURIComponent(version)}/evaluate`, {
    method: "POST",
    body: JSON.stringify({ operator }),
  });
}

export async function activateSkillVersion(
  skillId: string, version: string, operator: boolean, canary = false, reason = "",
) {
  return request(`/skills/${encodeURIComponent(skillId)}/patch/${encodeURIComponent(version)}/activate`, {
    method: "POST",
    body: JSON.stringify({ operator, canary, reason }),
  });
}

export async function promoteSkillCanary(skillId: string, version: string, operator: boolean) {
  return request(`/skills/${encodeURIComponent(skillId)}/patch/${encodeURIComponent(version)}/promote`, {
    method: "POST",
    body: JSON.stringify({ operator }),
  });
}

export async function checkSkillRollback(skillId: string, version: string, operator: boolean, userCorrections = 0) {
  return request(`/skills/${encodeURIComponent(skillId)}/patch/${encodeURIComponent(version)}/auto-rollback-check`, {
    method: "POST",
    body: JSON.stringify({ operator, userCorrections }),
  });
}

export interface AuthoringMeta {
  tools: string[];
  permissions: string[];
  categories: string[];
  riskLevels: string[];
}

export async function getAuthoringMeta(): Promise<AuthoringMeta> {
  return request<AuthoringMeta>("/skills/authoring/tools", { method: "GET" });
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

export async function createUserSkill(payload: AuthorSkillInput, operator: boolean) {
  return request<{ success: boolean; skillId: string; version: string; status: string }>("/skills/author", {
    method: "POST",
    body: JSON.stringify({ ...payload, operator }),
  });
}

export async function updateUserSkill(skillId: string, patch: Partial<AuthorSkillInput>, operator: boolean) {
  return request<{ success: boolean; skillId: string; version: string; status: string }>(
    `/skills/${encodeURIComponent(skillId)}/author`,
    { method: "PUT", body: JSON.stringify({ ...patch, operator }) }
  );
}

export async function deleteUserSkill(skillId: string, operator: boolean) {
  return request<{ success: boolean; skillId: string; deleted: boolean; status?: string; reason?: string }>(
    `/skills/${encodeURIComponent(skillId)}/author`,
    { method: "DELETE", body: JSON.stringify({ operator }) }
  );
}

export async function submitDraftReview(skillId: string, operator: boolean, reason: string, evaluationId?: string) {
  return request(`/skill-drafts/${encodeURIComponent(skillId)}/submit-review`, {
    method: "POST",
    body: JSON.stringify({ operator, reason, evaluationId }),
  });
}

export async function approveDraft(skillId: string, operator: boolean, requestId: string, notes = "") {
  return request(`/skill-drafts/${encodeURIComponent(skillId)}/approve`, {
    method: "POST",
    body: JSON.stringify({ operator, requestId, notes }),
  });
}

export async function rejectDraft(skillId: string, operator: boolean, requestId: string, reason: string) {
  return request(`/skill-drafts/${encodeURIComponent(skillId)}/reject`, {
    method: "POST",
    body: JSON.stringify({ operator, requestId, reason }),
  });
}

