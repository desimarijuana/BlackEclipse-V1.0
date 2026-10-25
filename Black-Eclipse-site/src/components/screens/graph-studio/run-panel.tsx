'use client';

// ── Execution console ────────────────────────────────────────────────────────
// The run surface: start a TEST run of the persisted version, watch node
// statuses, inspect inputs/outputs/errors per node, and cancel a running graph.
// It renders ONLY what the runtime reported — there is no optimistic "success".

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { Check, Play, SquareArrowOutUpRight, X } from '@/lib/icons';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { isTerminal, type GraphRunStatus, type NodeRunRecord, type NodeRunStatus } from '@/lib/graph-studio/execution-client';

const STATUS_TONE: Record<GraphRunStatus, string> = {
  pending: 'text-slate-400',
  queued: 'text-slate-300',
  running: 'text-sky-300',
  succeeded: 'text-emerald-300',
  failed: 'text-rose-300',
  cancelled: 'text-amber-300',
};

const NODE_TONE: Record<NodeRunStatus, string> = {
  pending: 'bg-slate-600',
  ready: 'bg-slate-400',
  running: 'bg-sky-400 animate-pulse',
  succeeded: 'bg-emerald-400',
  failed: 'bg-rose-400',
  cancelled: 'bg-amber-400',
  skipped: 'bg-slate-700',
};

function preview(value: unknown): string {
  if (value === undefined) return '—';
  try {
    const text = JSON.stringify(value);
    return text.length > 400 ? `${text.slice(0, 400)}…` : text;
  } catch {
    return String(value);
  }
}

function NodeRow({ nodeRun }: { nodeRun: NodeRunRecord }) {
  const [open, setOpen] = useState(false);
  const inputKeys = Object.keys(nodeRun.inputs ?? {});
  const outputKeys = Object.keys(nodeRun.outputs ?? {});
  return (
    <li className="rounded-md border border-white/10 bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left"
      >
        <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', NODE_TONE[nodeRun.status])} />
        <span className="min-w-0 flex-1 truncate text-[11px] text-foreground">{nodeRun.label || nodeRun.nodeId}</span>
        {nodeRun.attempt > 1 && <span className="shrink-0 text-[9.5px] text-amber-300">×{nodeRun.attempt}</span>}
        {typeof nodeRun.durationMs === 'number' && (
          <span className="shrink-0 text-[9.5px] text-muted-foreground">{nodeRun.durationMs} ms</span>
        )}
        <span className="shrink-0 text-[9.5px] text-muted-foreground">{nodeRun.status}</span>
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-white/10 px-2 py-1.5">
          {nodeRun.error && (
            <p className="rounded bg-rose-500/10 px-1.5 py-1 text-[10.5px] text-rose-200">
              {nodeRun.errorCode ? `${nodeRun.errorCode}: ` : ''}
              {nodeRun.error}
            </p>
          )}
          {inputKeys.length > 0 && (
            <div>
              <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">In</div>
              {inputKeys.map((key) => (
                <div key={key} className="truncate font-mono text-[10px] text-slate-300">
                  {key}: {preview(nodeRun.inputs[key])}
                </div>
              ))}
            </div>
          )}
          {outputKeys.length > 0 && (
            <div>
              <div className="text-[9.5px] uppercase tracking-wide text-muted-foreground">Out</div>
              {outputKeys.map((key) => (
                <div key={key} className="truncate font-mono text-[10px] text-slate-300">
                  {key}: {preview(nodeRun.outputs[key])}
                </div>
              ))}
            </div>
          )}
          {inputKeys.length === 0 && outputKeys.length === 0 && !nodeRun.error && (
            <p className="text-[10px] text-muted-foreground">No values captured.</p>
          )}
        </div>
      )}
    </li>
  );
}

export function RunPanel({
  onStart,
  onCancel,
  busy,
  canRun,
  blockReason,
}: {
  onStart: () => void;
  onCancel: () => void;
  busy: boolean;
  canRun: boolean;
  blockReason?: string | null;
}) {
  const run = useGraphEditor((s) => s.run);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
        <button
          type="button"
          disabled={!canRun || busy}
          onClick={onStart}
          title={blockReason ?? 'Run this workflow with the runtime\'s test-run permission envelope'}
          className="flex items-center gap-1.5 rounded-md border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1.5 text-[11px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-40"
        >
          {busy ? <Play size={12} /> : <Check size={12} />} Test run
        </button>
        {run && (
          <>
            <span className={cn('text-[11px]', STATUS_TONE[run.status])}>
              {run.status}
              {typeof run.durationMs === 'number' ? ` · ${run.durationMs} ms` : ''}
            </span>
            {!isTerminal(run.status) && (
              <button
                type="button"
                onClick={onCancel}
                className="ml-auto flex items-center gap-1 rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-[10.5px] text-rose-200 hover:bg-rose-500/20"
              >
                <X size={11} /> Cancel
              </button>
            )}
          </>
        )}
      </div>

      {!run && (
        <div className="px-3 py-3 text-[11px] leading-relaxed text-muted-foreground">
          <p>
            A test run executes the <strong className="text-foreground">saved version</strong> in the Python runtime.
            Nodes with network, write or trading effects are refused — a test run can inspect a graph, never act on the
            world.
          </p>
          {blockReason && <p className="mt-2 text-amber-300">{blockReason}</p>}
        </div>
      )}

      {run && (
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          {run.error && (
            <p className="mb-2 rounded-md border border-rose-500/25 bg-rose-500/10 px-2 py-1.5 text-[10.5px] text-rose-200">
              {run.error}
            </p>
          )}
          {run.output !== undefined && run.output !== null && (
            <details className="mb-2 rounded-md border border-emerald-500/20 bg-emerald-500/5 px-2 py-1.5" open>
              <summary className="cursor-pointer text-[10px] uppercase tracking-wide text-emerald-200">
                Terminal output
              </summary>
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] text-slate-300">
                {preview(run.output)}
              </pre>
            </details>
          )}
          <ul className="space-y-1">
            {(run.nodeRuns ?? []).map((nodeRun) => (
              <NodeRow key={nodeRun.nodeId} nodeRun={nodeRun} />
            ))}
          </ul>
          {(!run.nodeRuns || run.nodeRuns.length === 0) && (
            <p className="px-1 py-2 text-[11px] text-muted-foreground">Waiting for the runtime…</p>
          )}
          {(run.events ?? []).length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-[10px] uppercase tracking-wide text-muted-foreground">
                Log ({run.events?.length})
              </summary>
              <div className="mt-1 space-y-0.5">
                {(run.events ?? []).map((event, index) => (
                  <div key={`${event.at}-${index}`} className="flex gap-1.5 font-mono text-[9.5px] text-muted-foreground">
                    <span className="shrink-0 text-slate-500">{event.kind}</span>
                    <span className="min-w-0 flex-1 truncate">
                      {event.nodeId ? `${event.nodeId}: ` : ''}
                      {event.message}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
          <div className="mt-3 flex items-center gap-1 text-[9.5px] text-muted-foreground">
            <SquareArrowOutUpRight size={10} /> run {run.id}
          </div>
        </div>
      )}
    </div>
  );
}
