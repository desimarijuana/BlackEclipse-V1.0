// ── Graph assistant client ───────────────────────────────────────────────────
// The model proposal is produced and validated by the PYTHON runtime against
// the same registry the compiler uses. This client only transports the current
// graph + instruction and returns typed operations for the editor to apply.

import { readWorkflowIR } from './migrations';
import type { Diagnostic, WorkflowIR } from './types';
import type { GraphEditOp } from './assistant-ops';

export interface AssistantDiagnostic extends Diagnostic {
  severity: 'error' | 'warning';
}

export interface AssistantApproval {
  id: string;
  kind: string;
  status: string;
  title: string;
  summary: string;
  effect: string;
  risk: string;
  grantPattern?: string | null;
  grantLabel?: string | null;
}

export interface AssistantClarification {
  id: string;
  question: string;
  context?: string;
  options: string[];
  allowCustom?: boolean;
}

export interface AssistantResult {
  ok: boolean;
  mode: 'edit' | 'ask';
  answer: string;
  summary: string;
  ops: GraphEditOp[];
  ir?: WorkflowIR;
  diagnostics: AssistantDiagnostic[];
  errors: AssistantDiagnostic[];
  warnings: string[];
  focusNodeIds: string[];
  runs?: AssistantRunResult[];
  model?: { provider?: string; model?: string };
  approval?: AssistantApproval | null;
  clarification?: AssistantClarification | null;
}

export interface AssistantRunResult {
  run?: number;
  ok?: boolean;
  status?: string;
  error?: string | null;
  failed?: Array<{ nodeId?: string; label?: string; error?: string | null; errorCode?: string | null }>;
  nodes?: Array<{ nodeId?: string; type?: string; status?: string; error?: string | null; durationMs?: number | null }>;
  outputPreview?: string;
}

export interface AssistantTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface AssistantRunFailure {
  status?: string;
  failedNodeId?: string | null;
  error?: string | null;
  events?: string[];
}

export interface AssistantRequest {
  instruction: string;
  ir: WorkflowIR;
  mode?: 'edit' | 'ask';
  selection?: { nodeIds: string[]; edgeIds: string[] };
  history?: AssistantTurn[];
  lastRun?: AssistantRunFailure | null;
  requireApproval?: boolean;
  model?: { provider?: string; model?: string };
}

export type AssistantEvent =
  | { type: 'run'; runId: string; status?: string; workflowId?: string | null }
  | { type: 'status'; stage: string; label: string }
  | { type: 'text_delta'; text: string }
  | { type: 'tool_start'; name: string; label: string }
  | { type: 'tool_end'; name: string; label: string; ok: boolean; error?: string | null }
  | { type: 'approval_requested'; approval: AssistantApproval }
  | { type: 'approval_resolved'; approvalId: string; approved: boolean }
  | { type: 'cancelled'; reason?: string }
  | { type: 'result'; result: AssistantResult }
  | { type: 'error'; message: string };

function parseResult(data: unknown): AssistantResult {
  const body = (data ?? {}) as Partial<AssistantResult>;
  const ops = Array.isArray(body.ops) ? (body.ops as GraphEditOp[]) : [];
  return {
    ok: Boolean(body.ok),
    mode: body.mode === 'ask' ? 'ask' : 'edit',
    answer: typeof body.answer === 'string' ? body.answer : '',
    summary: typeof body.summary === 'string' ? body.summary : '',
    ops,
    ir: body.ir ? readWorkflowIR(body.ir) : undefined,
    diagnostics: Array.isArray(body.diagnostics) ? body.diagnostics : [],
    errors: Array.isArray(body.errors) ? body.errors : [],
    warnings: Array.isArray(body.warnings) ? body.warnings : [],
    focusNodeIds: Array.isArray(body.focusNodeIds) ? body.focusNodeIds : [],
    runs: Array.isArray(body.runs) ? (body.runs as AssistantRunResult[]) : [],
    model: body.model,
    approval: (body.approval as AssistantApproval | null | undefined) ?? null,
    clarification: (body.clarification as AssistantClarification | null | undefined) ?? null,
  };
}

function requestBody(request: AssistantRequest) {
  return JSON.stringify({
    instruction: request.instruction,
    mode: request.mode ?? 'edit',
    ir: request.ir,
    selection: request.selection ?? null,
    history: request.history ?? [],
    lastRun: request.lastRun ?? null,
    requireApproval: request.requireApproval === true,
    model: request.model ?? null,
  });
}

function cancelledResult(): AssistantResult {
  return {
    ok: false,
    mode: 'edit',
    answer: '',
    summary: 'Stopped.',
    ops: [],
    diagnostics: [],
    errors: [],
    warnings: [],
    focusNodeIds: [],
  };
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException
    ? err.name === 'AbortError'
    : err instanceof Error && err.name === 'AbortError';
}

/**
 * A dropped SSE connection is not a lost turn. The runtime keeps the validated
 * result on the run record, so poll the status endpoint once the stream dies and
 * return the same result the stream would have delivered.
 */
async function recoverAssistRun(runId: string, signal?: AbortSignal): Promise<AssistantResult | null> {
  const deadline = Date.now() + 5 * 60_000;
  for (;;) {
    if (signal?.aborted) return null;
    try {
      const res = await fetch(`/api/graphs/assist/runs/${encodeURIComponent(runId)}/status`, { signal });
      if (res.ok) {
        const data = (await res.json().catch(() => ({}))) as {
          status?: string;
          result?: unknown;
        };
        if (data.result) return parseResult(data.result);
        if (data.status === 'cancelled') return cancelledResult();
        if (data.status === 'failed' || data.status === 'completed') return null;
      }
    } catch (err) {
      if (isAbortError(err)) return null;
    }
    if (Date.now() > deadline) return null;
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
}

/**
 * Stream one assistant turn. Progress events arrive as each tool runs; the
 * final `result` event carries the same validated payload as the one-shot API.
 */
export async function assistGraphStream(
  request: AssistantRequest,
  handlers: { signal?: AbortSignal; onEvent?: (event: AssistantEvent) => void } = {},
): Promise<AssistantResult> {
  const res = await fetch('/api/graphs/assist/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: requestBody(request),
    signal: handlers.signal,
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { error?: string; detail?: unknown };
    const detail = typeof data.detail === 'string' ? data.detail : undefined;
    throw new Error(detail ?? data.error ?? `The workflow assistant failed (${res.status})`);
  }
  if (!res.body) throw new Error('The assistant returned no stream.');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: AssistantResult | null = null;
  let runId: string | null = null;

  const handle = (payload: AssistantEvent) => {
    handlers.onEvent?.(payload);
    if (payload.type === 'run') {
      runId = payload.runId;
    } else if (payload.type === 'result') {
      result = payload.result;
    } else if (payload.type === 'cancelled') {
      // A server-side stop is a terminal event, not a missing result. The store
      // appends its own "Stopped." message, so this only satisfies the return.
      result = cancelledResult();
    } else if (payload.type === 'error') {
      throw new Error(payload.message);
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const chunk = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data:')) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;
          try {
            handle(JSON.parse(raw) as AssistantEvent);
          } catch (err) {
            if (err instanceof SyntaxError) continue;
            throw err;
          }
        }
        boundary = buffer.indexOf('\n\n');
      }
    }
  } catch (err) {
    await reader.cancel().catch(() => {});
    if (!isAbortError(err) && runId) {
      const recovered = await recoverAssistRun(runId, handlers.signal);
      if (recovered) return recovered;
    }
    throw err;
  } finally {
    reader.releaseLock();
  }

  if (!result) {
    if (runId) {
      const recovered = await recoverAssistRun(runId, handlers.signal);
      if (recovered) return recovered;
    }
    throw new Error('The assistant stream ended without a result.');
  }
  return result;
}

export async function assistGraph(request: AssistantRequest): Promise<AssistantResult> {
  const res = await fetch('/api/graphs/assist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: requestBody(request),
  });
  const data = (await res.json().catch(() => ({}))) as Partial<AssistantResult> & {
    error?: string;
    detail?: string | { message?: string };
  };
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : data.detail?.message;
    throw new Error(detail ?? data.error ?? `The workflow assistant failed (${res.status})`);
  }
  return parseResult(data);
}

async function controlAssistRun(runId: string, action: 'pause' | 'resume' | 'cancel'): Promise<void> {
  const res = await fetch(`/api/graphs/assist/runs/${encodeURIComponent(runId)}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { error?: string; detail?: string };
    throw new Error(data.detail ?? data.error ?? `The assistant could not ${action}.`);
  }
}

export const pauseAssistRun = (runId: string) => controlAssistRun(runId, 'pause');
export const resumeAssistRun = (runId: string) => controlAssistRun(runId, 'resume');
export const cancelAssistRun = (runId: string) => controlAssistRun(runId, 'cancel');

export async function decideAssistantApproval(
  approvalId: string,
  approve: boolean,
  remember: boolean,
): Promise<{ approval?: { status?: string } }> {
  const res = await fetch(`/api/harness/mcp/approvals/${encodeURIComponent(approvalId)}/decide`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approve, remember }),
  });
  const data = (await res.json().catch(() => ({}))) as {
    approval?: { status?: string };
    error?: string;
    detail?: string;
  };
  if (!res.ok) {
    throw new Error(data.detail ?? data.error ?? 'The approval could not be recorded.');
  }
  return data;
}

export async function answerAssistantClarification(
  clarificationId: string,
  answer: string,
): Promise<void> {
  const res = await fetch(`/api/harness/mcp/approvals/${encodeURIComponent(clarificationId)}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer }),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { error?: string; detail?: string };
    throw new Error(data.detail ?? data.error ?? 'The answer could not be recorded.');
  }
}
