// ─── Workflow front-door types (Harness closeout Phase 5) ────────────────────
// The Python runtime owns workflow definitions, validation and compilation. This
// file declares only the shapes the Next.js proxy forwards/reads.

export type WorkflowStepKind =
  | "agent"
  | "skill"
  | "conditional"
  | "parallel"
  | "approval"
  | "retrieval";

export interface WorkflowStep {
  id: string;
  kind: WorkflowStepKind;
  instruction?: string;
  tools?: string[] | null;
  dependsOn?: string[];
  branches?: string[];
  condition?: Record<string, unknown> | null;
  approval?: Record<string, unknown> | null;
  skillId?: string | null;
  skillInput?: Record<string, unknown> | null;
  retry?: { maxAttempts?: number; backoffMs?: number };
  timeoutMs?: number;
  terminal?: boolean;
}

export interface Workflow {
  id: string;
  version: string;
  name?: string;
  description?: string;
  agentId?: string;
  steps: WorkflowStep[];
}

export interface WorkflowSummary {
  id: string;
  version: string;
  name: string | null;
  description: string | null;
  createdAt: string;
}

export interface WorkflowRunResult {
  workflowId: string;
  status: string;
  steps?: Array<Record<string, unknown>>;
  outputs?: Record<string, string>;
  runIds?: string[];
  error?: { code?: string; message?: string } | null;
  note?: string;
}
