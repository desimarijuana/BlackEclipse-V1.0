// ─── Skill system TS-side contracts (Phase 3) ───────────────────────────────
// The skill registry, permissions and lifecycle live in Python
// (`python/harness/skills/`). This file declares only the shapes the Next.js
// front door needs to proxy and render — there is no skill logic here.

export type SkillStatus =
  | "draft"
  | "evaluating"
  | "testing"
  | "canary"
  | "review"
  | "validated"
  | "approved"
  | "enabled"
  | "active"
  | "disabled"
  | "deprecated"
  | "superseded"
  | "rolled_back"
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
  /** Load tier, for provenance labelling. `project` = repository-local. */
  provenance?: "bundled" | "profile" | "project" | "generated" | "external";
}

/** Project-local skill discovery + trust state (Phase 2). */
export interface ProjectSkillRoot {
  path: string;
  trusted: boolean;
  skillsDir: string;
  skillIds: string[];
  errors: string[];
  drift?: boolean;
  trustedHash?: string | null;
  currentHash?: string | null;
}

export interface ProjectSkillDiscovery {
  root: string | null;
  trustedRoot: boolean;
  drift?: boolean;
  roots: ProjectSkillRoot[];
  trustedSkillIds: string[];
  notices: string[];
}

export interface ProjectSkillTrustRecord {
  path: string;
  trusted: boolean;
  trustedAt: string | null;
  note: string | null;
  trustedHash?: string | null;
  revokedHash?: string | null;
}

export interface ProjectSkillDriftStatus {
  path: string;
  trusted: boolean;
  drift: boolean;
  trustedHash: string | null;
  currentHash: string | null;
  skillIds: string[];
}

/** Advisory content-scan finding (Phase 3). A clean scan is NOT proof of safety. */
export interface SkillContentFinding {
  category: string;
  severity: "warn" | "quarantine" | string;
  reason: string;
  snippet: string;
  location: string;
}

export interface SkillContentScan {
  ok: boolean;
  shouldQuarantine: boolean;
  categories: string[];
  findings: SkillContentFinding[];
  note?: string;
}

/** Learning journey / provenance graph node (Phase 6). Derived, read-only. */
export interface JourneyNode {
  id: string;
  kind:
    | "memory" | "skill" | "skill_version" | "correction" | "mistake"
    | "learning_candidate" | "evaluation" | "promotion" | "execution" | "session";
  label: string;
  status: string;
  scope?: string | null;
  createdAt?: string | null;
  [key: string]: unknown;
}

export interface JourneyEdge {
  source: string;
  target: string;
  relation: string;
}

export interface LearningJourney {
  nodes: JourneyNode[];
  edges: JourneyEdge[];
  clusters: Array<{ kind: string; count: number }>;
  generatedAt?: string;
  watermark?: string;
  stats: {
    nodeCount: number;
    edgeCount: number;
    byKind: Record<string, number>;
    byRelation: Record<string, number>;
    truncated: boolean;
  };
}

/** Guided `/learn` request + result (Phase 4). Always produces an inert draft. */
export interface LearnRequest {
  sourceKind: "run" | "document" | "repository" | "repeated_workflow" | "correction";
  title: string;
  objective?: string;
  procedure?: string[];
  content?: string;
  sourceRunId?: string;
  tools?: string[];
  category?: string;
  scopeNote?: string;
}

export interface LearnDraftResult {
  ok: boolean;
  draft?: SkillDraft;
  issues?: string[];
  reusable?: boolean;
  candidateId?: string;
  sourceKind?: string;
  sanitized?: string[];
  lint?: string[];
  error?: string;
}

/** A skill bundle: a named, ordered reference to existing skills (Phase 3). */
export interface SkillBundle {
  id: string;
  name: string;
  description: string;
  skills: string[];
  instruction: string;
  constraints: string;
  provenance: "manual" | "profile" | "project" | "imported";
  version: string;
  memberVersions: Record<string, string>;
  locked: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface SkillBundleResolution {
  bundleId: string;
  ok: boolean;
  resolved: string[];
  missing: string[];
  unavailable: string[];
  provenance: string;
  chars: number;
  version?: string;
  locked?: boolean;
  drifted?: boolean;
  compatible?: boolean;
  incompatible?: string[];
  resolvedVersions?: Record<string, string>;
}

export interface SkillBundleListResponse {
  bundles: SkillBundle[];
  resolved: Record<string, SkillBundleResolution>;
}

export interface ProjectSkillStatus {
  projectDiscovery: boolean;
  projectRoot: string | null;
  discovery: ProjectSkillDiscovery;
  drift?: ProjectSkillDriftStatus | null;
  trusted: ProjectSkillTrustRecord[];
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

// ── Versioned patches (M2) ──────────────────────────────────────────────────

export interface SkillPatchOperation {
  op: "replace" | "add" | "remove";
  path: string;
  value?: unknown;
}

export interface SkillPatch {
  skill: string;
  baseVersion: string;
  operations: SkillPatchOperation[];
  reason: string;
  evidenceRuns: string[];
  regressionCases: string[];
  author: string;
}

export interface SkillVersionHistoryEntry {
  version: string;
  status: SkillStatus;
  isActive: boolean;
  evaluationStatus: EvaluationStatus | null;
  baseVersion: string | null;
  patchSummary: string | null;
  patchAuthor: string | null;
  reviewId: string | null;
  canaryState: string | null;
  activatedAt: string | null;
  rolledBackAt: string | null;
  createdAt: string;
  patch: SkillPatch | null;
}

export interface SkillPatchResult {
  ok: boolean;
  skillId?: string;
  version?: string;
  baseVersion?: string;
  status?: string;
  patch?: SkillPatch;
  error?: string;
  stage?: string;
  stale?: boolean;
  canary?: boolean;
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
  provenance?: "bundled" | "profile" | "project" | "generated" | "external";
  contentScan?: SkillContentScan | null;
  dependencyGraph?: SkillDependencyGraph;
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

/** Skill dependency graph / preflight (Phase 14). Read-only. */
export interface SkillDependencyNode {
  id: string;
  version: string | null;
  status: string;
  executable: boolean;
  missing: boolean;
  requiredTools: string[];
  permissions: string[];
}

export interface SkillDependencyEdge {
  from: string;
  to: string;
  constraint: string | null;
  optional: boolean;
  resolvedVersion: string | null;
  status: "ok" | "optional" | "missing" | "disabled" | "incompatible" | string;
}

export interface SkillDependencyGraph {
  skillId: string;
  ok: boolean;
  nodes: SkillDependencyNode[];
  edges: SkillDependencyEdge[];
  order: Array<{ skillId: string; version: string | null }>;
  errors: string[];
  cycles: string[];
  missing: string[];
  disabled: string[];
  versionMismatches: string[];
}

/** Cold-start onboarding content (Phase 13). Static, read-only. */
export interface OnboardingStep {
  id: string;
  title: string;
  body: string;
}

export interface OnboardingContent {
  version: number;
  steps: OnboardingStep[];
  starterSkills: Array<{
    id: string; name: string; description: string; category: string; provenance: string;
  }>;
  note: string;
}

/** Skill quality over time (Phase 6). Derived from real execution rows. */
export interface SkillQualityMetrics {
  skillId: string;
  version: string | null;
  executions: number;
  completed: number;
  failed: number;
  successRate: number | null;
  failureRate: number | null;
  outputValidationRate: number | null;
  invalidOutputCount: number;
  toolBudgetFailureRate: number | null;
  meanDurationMs: number | null;
  meanToolCalls: number | null;
  failureCauses: Record<string, number>;
  sampleReliable: boolean;
  successInterval: [number, number] | null;
  sampleWarning: string | null;
  trend: Array<{ day: string; total: number; completed: number; successRate: number | null }>;
  timeWeightedSuccessRate: number | null;
  usefulness: { score: number | null; reason: string };
  deprecation: { recommend: boolean; reason: string };
}

export interface SkillQualityComparison {
  skillId: string;
  older: string;
  newer: string;
  before: SkillQualityMetrics;
  after: SkillQualityMetrics;
  caseComparison: {
    sharedCases: string[];
    addedCases: string[];
    removedCases: string[];
    caseRegressions: Array<{ caseId: string; before: string; after: string }>;
    comparable: boolean;
  };
  regressions: string[];
  regressed: boolean;
  lowSampleVersions: string[];
}

export interface SkillPromotionEvidence {
  skillId: string;
  version: string;
  evaluation: { status: string | null; summary: string | null; dimensions: unknown[] } | null;
  executionMetrics: SkillQualityMetrics;
  deprecation: { recommend: boolean; reason: string };
  usefulness: { score: number | null; reason: string };
  sample: { executions: number; reliable: boolean; warning: string | null; successInterval: [number, number] | null };
  trend: SkillQualityMetrics["trend"];
  failureCauses: Record<string, number>;
  note: string;
}

export interface SkillListResponse {
  skills: SkillSummary[];
  loadErrors: string[];
  duplicates: string[];
  projectNotices?: string[];
  projectDrift?: boolean;
  shadowed?: string[];
  contentFindings?: Record<string, SkillContentScan>;
  quarantined?: string[];
}
