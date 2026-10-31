'use client';

// ── Execution dock ───────────────────────────────────────────────────────────
// A collapsible bottom dock, not a tab in a cramped rail. It shows the run at a
// glance while collapsed and hands the full console to the existing RunPanel
// when expanded. The runtime stays the single source of truth.

import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { ChevronDown, ChevronUp, Play, Square } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import type { GraphRunStatus } from '@/lib/graph-studio/execution-client';
import { RunPanel } from './run-panel';
import { ScheduleList } from './schedule-list';

const STATUS_TONE: Record<GraphRunStatus, string> = {
  pending: 'text-slate-400',
  queued: 'text-slate-300',
  running: 'text-sky-300',
  succeeded: 'text-emerald-300',
  failed: 'text-rose-300',
  cancelled: 'text-amber-300',
};

export function ExecutionDock({
  onStart,
  onCancel,
  busy,
  canRun,
  blockReason,
  workflowId,
  runInputText,
  onRunInputChange,
  runInputError,
}: {
  onStart: () => void;
  onCancel: () => void;
  busy: boolean;
  canRun: boolean;
  blockReason?: string | null;
  workflowId: string | null;
  /** One-off trigger input for the next run (JSON text in the run panel). */
  runInputText: string;
  onRunInputChange: (value: string) => void;
  runInputError?: string | null;
}) {
  const run = useGraphEditor((s) => s.run);
  const [expanded, setExpanded] = useState(false);
  const runId = run?.id;

  useEffect(() => {
    if (runId) setExpanded(true);
  }, [runId]);

  const counts = useMemo(() => {
    const statuses = Object.values(run?.nodeStatus ?? {});
    const nodeRuns = run?.nodeRuns ?? [];
    const done = nodeRuns.length > 0
      ? nodeRuns.filter((item) => item.status === 'succeeded').length
      : statuses.filter((status) => status === 'succeeded').length;
    const failed = nodeRuns.length > 0
      ? nodeRuns.filter((item) => item.status === 'failed').length
      : statuses.filter((status) => status === 'failed').length;
    return { done, failed, running: statuses.filter((status) => status === 'running').length, total: nodeRuns.length || statuses.length };
  }, [run]);

  return (
    <div className="shrink-0 border-t border-white/10 bg-background/60">
      <div className="flex h-9 items-center gap-2 px-3">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {expanded ? <ChevronDown size={12} className="shrink-0 text-muted-foreground" /> : <ChevronUp size={12} className="shrink-0 text-muted-foreground" />}
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Execution</span>
          {run ? (
            <>
              <span className={cn('flex items-center gap-1 text-[10.5px]', STATUS_TONE[run.status])}>
                <span className={cn(
                  'h-1.5 w-1.5 rounded-full',
                  run.status === 'running' ? 'animate-pulse bg-sky-400'
                    : run.status === 'succeeded' ? 'bg-emerald-400'
                      : run.status === 'failed' ? 'bg-rose-400'
                        : run.status === 'cancelled' ? 'bg-amber-400' : 'bg-slate-500',
                )} />
                {run.status}
              </span>
              {typeof run.durationMs === 'number' && <span className="text-[10px] text-muted-foreground">{run.durationMs} ms</span>}
              {counts.total > 0 && <span className="text-[10px] text-muted-foreground">{counts.done}/{counts.total} nodes{counts.failed ? ` · ${counts.failed} failed` : ''}</span>}
            </>
          ) : (
            <span className="text-[10.5px] text-muted-foreground">No run yet</span>
          )}
        </button>
        {run && run.status === 'running' ? (
          <Button type="button" variant="destructive" size="xs" onClick={onCancel}>
            <Square size={10} /> Cancel
          </Button>
        ) : (
          <Button type="button" size="xs" disabled={!canRun || busy} onClick={onStart} title={blockReason ?? 'Test run of the saved version'}>
            <Play size={10} /> Test run
          </Button>
        )}
      </div>

      {expanded && (
        <div className="flex h-[320px] min-h-0 flex-col border-t border-white/10">
          <div className="min-h-0 flex-1">
            <RunPanel
              onStart={onStart}
              onCancel={onCancel}
              busy={busy}
              canRun={canRun}
              blockReason={blockReason}
              runInputText={runInputText}
              onRunInputChange={onRunInputChange}
              runInputError={runInputError}
            />
          </div>
          <div className="max-h-[132px] shrink-0 overflow-y-auto">
            <ScheduleList workflowId={workflowId} />
          </div>
        </div>
      )}
    </div>
  );
}
