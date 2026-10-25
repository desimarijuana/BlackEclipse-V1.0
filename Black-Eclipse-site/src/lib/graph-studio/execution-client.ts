// ── Graph execution client ───────────────────────────────────────────────────
// Browser-side wrappers for the workflow run surface. The routes load the
// persisted IR server-side and forward it to the Python runtime; this module
// only carries DTOs and errors, so the UI can render real run state.

export type NodeRunStatus =
  | 'pending' | 'ready' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'skipped';

export type GraphRunStatus = 'pending' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

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
  /** A successful node whose checkpoint can resume a retried run. */
  resumable?: boolean;
}

export interface RunEventRecord {
  /** Persisted event id (the SSE cursor). */
  id?: number;
  at: string;
  kind: string;
  nodeId?: string | null;
  message: string;
}

export type GraphStreamEvent = RunEventRecord;

export interface GraphRunStreamHandlers {
  onEvent: (event: GraphStreamEvent) => void;
  onEnd?: () => void;
  onError?: (error: Error) => void;
}

/** Live node status for a graph event, or null when the event is not a
 *  node-lifecycle transition. */
export function nodeStatusFromEvent(kind: string): NodeRunStatus | null {
  switch (kind) {
    case 'node.started':
    case 'node.retry':
      return 'running';
    case 'node.succeeded':
      return 'succeeded';
    case 'node.failed':
      return 'failed';
    case 'node.cancelled':
      return 'cancelled';
    case 'node.skipped':
      return 'skipped';
    default:
      return null;
  }
}

/** A run-level event that means the next read is authoritative. */
export function isRunTerminalEvent(kind: string): boolean {
  return (
    kind === 'run.succeeded' ||
    kind === 'run.failed' ||
    kind === 'run.cancelled' ||
    kind === 'run.timeout' ||
    kind === 'run.stopped'
  );
}

/** Open the run's SSE stream. Returns a close handle. The runtime owns the
 *  event log; this only consumes its frames. */
export function openGraphRunStream(
  runId: string,
  handlers: GraphRunStreamHandlers,
): () => void {
  if (typeof EventSource === 'undefined') {
    handlers.onError?.(new Error('EventSource is unavailable in this environment'));
    return () => {};
  }
  const source = new EventSource(`/api/graph-runs/${encodeURIComponent(runId)}/stream`);
  source.onmessage = (message: MessageEvent<string>) => {
    let event: GraphStreamEvent;
    try {
      event = JSON.parse(message.data) as GraphStreamEvent;
    } catch {
      return;
    }
    if (event.kind === 'stream.end') {
      source.close();
      handlers.onEnd?.();
      return;
    }
    handlers.onEvent(event);
  };
  source.onerror = () => {
    handlers.onError?.(new Error('live stream disconnected'));
  };
  return () => source.close();
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
  /** Terminal value(s): one terminal -> its value, multiple -> {nodeId: value}. */
  output?: unknown;
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

export interface StartRunOptions {
  /** Explicit operator run. The server still derives grants from the graph. */
  operator?: boolean;
  allowNetwork?: boolean;
  allowPaperTrading?: boolean;
}

/** Start a TEST run (default) or an explicitly authorized operator run. */
export async function startWorkflowRun(
  workflowId: string,
  version?: number,
  options: StartRunOptions = {},
): Promise<GraphRunRecord> {
  const data = await request<{ run: GraphRunRecord }>(`/api/workflows/${workflowId}/runs`, {
    method: 'POST',
    body: JSON.stringify({ version, ...options }),
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
