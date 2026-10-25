// ── Post-run step inspector ──────────────────────────────────────────────────
// A persisted run already carries every node's bounded inputs/outputs, status,
// error and its events. This module turns that record into an ordered list of
// steps so the UI can step through a finished (or partially failed) run without
// re-executing anything.

import type { GraphRunRecord, NodeRunRecord, NodeRunStatus, RunEventRecord } from './execution-client';

export interface RunStep {
  index: number;
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
  /** True when this successful node saved a resumable checkpoint. */
  checkpointed: boolean;
  events: RunEventRecord[];
}

export interface RunStepSummary {
  total: number;
  succeeded: number;
  failed: number;
  skipped: number;
  checkpointed: number;
}

function orderKey(node: NodeRunRecord): [number, number, string] {
  const started = node.startedAt ? Date.parse(node.startedAt) : Number.POSITIVE_INFINITY;
  return [node.layer ?? 0, Number.isFinite(started) ? started : Number.MAX_SAFE_INTEGER, node.nodeId];
}

/** Build the ordered step list for a run record. */
export function buildRunSteps(run: GraphRunRecord): RunStep[] {
  const nodes = [...(run.nodeRuns ?? [])].sort((a, b) => {
    const [al, at, aid] = orderKey(a);
    const [bl, bt, bid] = orderKey(b);
    if (al !== bl) return al - bl;
    if (at !== bt) return at - bt;
    return aid.localeCompare(bid);
  });
  const events = run.events ?? [];
  const eventsByNode = new Map<string, RunEventRecord[]>();
  for (const event of events) {
    if (!event.nodeId) continue;
    const list = eventsByNode.get(event.nodeId) ?? [];
    list.push(event);
    eventsByNode.set(event.nodeId, list);
  }
  return nodes.map((node, index) => ({
    index,
    nodeId: node.nodeId,
    nodeType: node.nodeType,
    label: node.label || node.nodeId,
    status: node.status,
    layer: node.layer ?? 0,
    attempt: node.attempt ?? 1,
    startedAt: node.startedAt,
    finishedAt: node.finishedAt,
    durationMs: node.durationMs,
    inputs: node.inputs ?? {},
    outputs: node.outputs ?? {},
    error: node.error,
    errorCode: node.errorCode,
    checkpointed: Boolean(node.resumable),
    events: eventsByNode.get(node.nodeId) ?? [],
  }));
}

export function summarizeRunSteps(steps: RunStep[]): RunStepSummary {
  return {
    total: steps.length,
    succeeded: steps.filter((step) => step.status === 'succeeded').length,
    failed: steps.filter((step) => step.status === 'failed').length,
    skipped: steps.filter((step) => step.status === 'skipped').length,
    checkpointed: steps.filter((step) => step.checkpointed).length,
  };
}

/** The step index for a node, or -1 when the node never ran. */
export function stepIndexFor(steps: RunStep[], nodeId: string): number {
  return steps.findIndex((step) => step.nodeId === nodeId);
}
