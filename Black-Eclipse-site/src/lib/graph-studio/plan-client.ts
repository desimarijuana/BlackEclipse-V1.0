// Chat-to-graph client. The model proposal is validated by the PYTHON runtime
// against the same registry the compiler uses; this client only transports the
// objective and returns the validated IR or the runtime's diagnostics.

import { readWorkflowIR } from './migrations';
import type { WorkflowIR } from './types';

export interface GraphPlanError {
  message: string;
  code?: string;
  nodeId?: string | null;
}

export interface GraphPlanResult {
  ok: boolean;
  ir?: WorkflowIR;
  errors: GraphPlanError[];
  warnings: string[];
  nodeCount?: number;
  edgeCount?: number;
  executionMode?: string;
  model?: { provider?: string; model?: string };
}

export async function planGraph(objective: string): Promise<GraphPlanResult> {
  const res = await fetch('/api/graphs/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ objective }),
  });
  const data = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    ir?: unknown;
    errors?: GraphPlanError[];
    warnings?: string[];
    nodeCount?: number;
    edgeCount?: number;
    executionMode?: string;
    model?: { provider?: string; model?: string };
    error?: string;
    detail?: string | { message?: string };
  };
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : data.detail?.message;
    throw new Error(detail ?? data.error ?? `Graph planning failed (${res.status})`);
  }
  return {
    ok: Boolean(data.ok),
    ir: data.ok && data.ir ? readWorkflowIR(data.ir) : undefined,
    errors: Array.isArray(data.errors) ? data.errors : [],
    warnings: Array.isArray(data.warnings) ? data.warnings : [],
    nodeCount: data.nodeCount,
    edgeCount: data.edgeCount,
    executionMode: data.executionMode,
    model: data.model,
  };
}
