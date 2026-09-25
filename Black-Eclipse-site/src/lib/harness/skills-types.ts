// ─── Skill system TS-side contracts (Phase 3) ───────────────────────────────
// The skill registry, permissions and lifecycle live in Python
// (`python/harness/skills/`). This file declares only the shapes the Next.js
// front door needs to proxy and render — there is no skill logic here.

export type SkillStatus =
  | "draft"
  | "testing"
  | "review"
  | "validated"
  | "enabled"
  | "disabled"
  | "deprecated"
  | "rejected";

export type SkillRisk = "low" | "medium" | "high" | "critical";

export type SkillCategory = "research" | "quality" | "finance" | "system";

export type EvaluationStatus =
  | "not_evaluated"
  | "passed"
  | "failed"
  | "needs_review"
  | "blocked";

export type ExecutionMode = "interactive" | "workflow" | "scheduled" | "agent" | "evaluation";

export interface SkillSummary {
  id: string;
  name: string;
  version: string;
  description: string;
  category: SkillCategory;
  tags: string[];
  status: SkillStatus;
  riskLevel: SkillRisk;
  permissions: string[];
  requiredTools: string[];
  evaluationStatus: EvaluationStatus;
  executable?: boolean;
  latestVersion?: string;
  versions?: string[];
  origin?: "builtin" | "author" | "learning";
}

export interface SkillValidationCheck {
  check: string;
  ok: boolean;
  detail: string;
}

export interface SkillValidation {
  ok: boolean;
  skillId: string;
  version: string;
  checks: SkillValidationCheck[];
  errors: string[];
}

export interface SkillDependencySpec {
  skillId: string;
  version?: string | null;
  optional?: boolean;
}

export interface SkillVersionRecord {
  version: string;
  status: SkillStatus;
  evaluationStatus: EvaluationStatus;
  contentHash: string;
  createdAt: string;
  origin: string;
  author: string | null;
}

export interface SkillExecutionRecord {
  id: string;
  runId: string;
  skillId: string;
  version: string;
  manifestHash: string | null;
  parentRunId: string | null;
  executionMode: ExecutionMode;
  status: string;
  actor: string | null;
  input?: Record<string, unknown>;
  output: string | null;
  error?: { code: string; message: string } | null;
  warnings?: string[];
  missingData?: string[];
  limitations?: string[];
  evidence?: unknown[];
  durationMs: number;
  traceId: string | null;
  createdAt: string;
  finishedAt: string | null;
  /** Whether the output was validated against the declared schema. null = not recorded (pre-migration). */
  outputValidated?: boolean | null;
  /** Bounded run metrics: toolCalls, toolErrors, modelSteps, totalTokens, durationMs. */
  metrics?: { toolCalls?: number; toolErrors?: number; modelSteps?: number; totalTokens?: number; durationMs?: number } | null;
}

export interface SkillEvaluationDimension {
  name: string;
  status: "passed" | "failed" | "needs_review" | "blocked";
  detail: string;
  mandatory?: boolean;
}

export interface SkillEvaluationRecord {
  id: string;
  skillId: string;
  version: string;
  status: "passed" | "failed" | "needs_review" | "blocked";
  evaluator: string;
  dimensions: SkillEvaluationDimension[];
  summary: string | null;
  createdAt: string;
  cases?: SkillEvaluationCase[];
}

export interface SkillEvaluationCase {
  caseId: string;
  name: string;
  kind: string;
  status?: string;
  expected?: unknown;
  actual?: unknown;
  error?: string | null;
}

export interface LearningCandidate {
  id: string;
  sourceRunId: string | null;
  candidateType: string;
  title: string;
  problem: string | null;
  observedBehavior: string | null;
  proposedLesson: string | null;
  proposedProcedure?: Array<Record<string, unknown>> | null;
  evidenceReferences: Array<Record<string, unknown>>;
  confidence: number;
  generalizationNotes: string | null;
  knownLimitations: string | null;
  /** Phase 7: structured failure diagnostics the run recorded (provider/category). */
  diagnostics?: Array<Record<string, unknown>> | null;
  /** Phase 7: the regional/provider scope the lesson is supported by. */
  scope?: { markets?: string[]; scopeClaim?: string } | null;
  status: string;
  createdAt: string;
  reviewedAt: string | null;
  resultingSkillId: string | null;
  resultingSkillVersion: string | null;
  draftManifest?: SkillDraft | null;
}

export interface SkillDraft {
  id: string;
  name: string;
  version: string;
  description: string;
  category: SkillCategory;
  status: "draft";
  evaluationStatus: "not_evaluated";
  origin: "learning";
  requiredTools: string[];
  permissions: string[];
  riskLevel: SkillRisk;
  sourceRunId?: string | null;
  knownLimitations?: string;
  generationIssues?: string[];
}

export interface SkillReviewRecord {
  id: string;
  skillId: string;
  version: string;
  actor: string | null;
  decision: string;
  notes: string | null;
  createdAt: string;
}

export interface SkillEventRecord {
  id: string;
  skillId: string | null;
  version: string | null;
  runId: string | null;
  type: string;
  at: string;
  data: Record<string, unknown>;
}

/** The full detail payload returned by GET /skills/:id. */
export interface SkillDetail extends Omit<SkillSummary, "versions"> {
  instructions: string;
  storedStatus: SkillStatus;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown> | null;
  requiredSkills: SkillDependencySpec[];
  limits: { maxSteps: number; timeoutMs: number; maxToolCalls: number };
  author: string;
  compatibleRuntime: string;
  sourceRunId: string | null;
  deprecation: { reason: string; supersededBy?: string | null; deprecatedAt?: string | null } | null;
  validation: SkillValidation;
  versions: SkillVersionRecord[];
  executions: SkillExecutionRecord[];
  evaluations: SkillEvaluationRecord[];
  reviews: SkillReviewRecord[];
  events: SkillEventRecord[];
}

/** The workflow-ready execution request (mirrors the Python contract). */
export interface SkillExecutionRequest {
  skillId: string;
  version?: string;
  input?: Record<string, unknown>;
  runId?: string;
  parentRunId?: string;
  executionMode?: ExecutionMode;
  userId?: string;
  timeoutMs?: number;
  metadata?: Record<string, unknown>;
}

export interface SkillExecutionResult {
  status: string;
  skillId: string;
  version?: string | null;
  runId?: string | null;
  traceId?: string | null;
  output?: string | null;
  outputValidated: boolean;
  error?: { code: string; message: string } | null;
  evidence: unknown[];
  warnings: string[];
  missingData: string[];
  limitations: string[];
  metrics: Record<string, unknown>;
}

export interface SkillListResponse {
  skills: SkillSummary[];
  loadErrors: string[];
  duplicates: string[];
}
