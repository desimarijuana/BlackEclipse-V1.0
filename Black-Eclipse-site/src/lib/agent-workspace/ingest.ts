// ── Agent Workspace — raw-frame ingest seam ──────────────────────────────────
// The chat transport (`lib/agent/registry.ts`) calls this for every raw harness
// frame it reads. It is the ONLY glue between the existing SSE stream and the
// workspace store: bind the frame's run, normalize it, hand it to the store.
//
// Keeping this out of `useAgentRun` means every chat surface (the ChatBot tab,
// the floating dock, future surfaces) feeds the workspace with no per-surface
// wiring, and `useAgentRun` stays a thin streaming hook.

'use client';

import { normalizeWorkspaceEvent } from './normalize';
import { useWorkspaceStore } from './store';
import { shouldIngestRun } from '@/lib/agent/run-focus';

/** Pull the run id out of a raw frame (envelope top level, or inner payload). */
function frameRunId(data: Record<string, unknown>): string | undefined {
  if (typeof data.runId === 'string') return data.runId;
  const inner = data.data;
  if (inner && typeof inner === 'object') {
    const id = (inner as Record<string, unknown>).runId;
    if (typeof id === 'string') return id;
  }
  return undefined;
}

/** Feed one raw harness frame to the live workspace. Never throws. */
export function ingestHarnessFrame(event: string, data: Record<string, unknown>): void {
  try {
    const runId = frameRunId(data);
    // Parallel conversations share one workspace projection. Only the focused
    // conversation's run may bind/ingest; another chat's stream must not reset
    // the panel or merge its tool activity into this one.
    if (!shouldIngestRun(runId)) return;
    const store = useWorkspaceStore.getState();
    if (runId) store.bindRun(runId);
    const events = normalizeWorkspaceEvent(event, data, Date.now());
    if (events.length === 0) return;
    store.ingest(events, {
      id: typeof data.id === 'string' ? data.id : undefined,
      seq: typeof data.seq === 'number' ? data.seq : undefined,
    });
  } catch {
    // A malformed frame must never break the chat stream.
  }
}
