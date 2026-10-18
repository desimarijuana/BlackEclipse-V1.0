// ── Graph execution client ───────────────────────────────────────────────────
// Browser-side wrappers for the workflow run surface. The routes load the
// persisted IR server-side and forward it to the Python runtime; this module
// only carries DTOs and errors, so the UI can render real run state.

export type NodeRunStatus =
  | 'pending' | 'ready' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'skipped';

export type GraphRunStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface NodeRunRecord {
  nodeId: string;
  nodeType: string;
  label: string;
  status: NodeRunStatus;
  layer: number;
  attempt: number;
  startedAt?: string | null;
  finishedAt?: string | null;
  durationMs?: number | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  error?: string | null;
  errorCode?: string | null;
}

export interface RunEventRecord {
  at: string;
  kind: string;
  nodeId?: string | null;
  message: string;
}

export interface PlanDiagnostic {
  severity: 'error' | 'warning';
  code: string;
  message: string;
  nodeId?: string | null;
  edgeId?: string | null;
}

export interface GraphRunRecord {
  id: string;
  workflowId: string;
  workflowVersion?: number | null;
  irVersion: number;
  mode: string;
  testRun: boolean;
  status: GraphRunStatus;
  startedAt: string;
  finishedAt?: string | null;
  durationMs?: number | null;
  error?: string | null;
  ownerId?: string;
  nodeRuns?: NodeRunRecord[];
  events?: RunEventRecord[];
  nodeStatus?: Record<string, NodeRunStatus>;
  plan?: { executable: boolean; layers: string[][]; diagnostics: PlanDiagnostic[] } | null;
}

export class GraphRunApiError extends Error {
  constructor(message: string, readonly status: number, readonly plan?: unknown) {
    super(message);
    this.name = 'GraphRunApiError';
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: unknown; error?: string }).detail;
    const message =
      typeof detail === 'string'
        ? detail
        : (detail as { message?: string } | undefined)?.message ??
          (data as { error?: string }).error ??
          `Request failed (${res.status})`;
    throw new GraphRunApiError(message, res.status, (detail as { plan?: unknown } | undefined)?.plan);
  }
  return data as T;
}

/** Start a TEST run of a workflow's persisted version. */
export async function startWorkflowRun(workflowId: string, version?: number): Promise<GraphRunRecord> {
  const data = await request<{ run: GraphRunRecord }>(`/api/workflows/${workflowId}/runs`, {
    method: 'POST',
    body: JSON.stringify({ version }),
  });
  return data.run;
}

export async function getGraphRun(runId: string): Promise<GraphRunRecord> {
  const data = await request<{ run: GraphRunRecord }>(`/api/graph-runs/${runId}`);
  return data.run;
}

export async function cancelGraphRun(runId: string): Promise<GraphRunRecord> {
  const data = await request<{ run: GraphRunRecord }>(`/api/graph-runs/${runId}/cancel`, { method: 'POST' });
  return data.run;
}

export async function listWorkflowRuns(workflowId: string): Promise<GraphRunRecord[]> {
  const data = await request<{ runs: GraphRunRecord[] }>(`/api/workflows/${workflowId}/runs`);
  return data.runs ?? [];
}

/** Terminal run states — polling stops here. */
export function isTerminal(status: GraphRunStatus): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled';
}
