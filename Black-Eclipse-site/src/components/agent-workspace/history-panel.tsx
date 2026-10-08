'use client';

// ── Agent Workspace — Run history panel ────────────────────────────────────────
// Lists recent runs and opens one for replay. Opening reconstructs the run's
// workspace from its persisted event trace (the runtime already stores it), so a
// finished run is inspectable without re-executing anything.

import { useEffect, useMemo, useState } from 'react';
import { ChevronRight, History, Loader2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { listWorkspaceRuns, type WorkspaceRunRow } from '@/lib/agent-workspace/history';

function statusClass(status: string | undefined): string {
  switch (status) {
    case 'completed':
      return 'text-emerald-300/80';
    case 'failed':
      return 'text-rose-300/80';
    case 'cancelled':
      return 'text-muted-foreground/60';
    default:
      return 'text-primary/80';
  }
}

export function HistoryPanel({
  onOpenRun,
  activeRunId,
}: {
  onOpenRun: (runId: string) => void;
  activeRunId?: string | null;
}) {
  const t = useT();
  const [runs, setRuns] = useState<WorkspaceRunRow[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    listWorkspaceRuns()
      .then((rows) => {
        if (alive) setRuns(rows);
      })
      .catch(() => {
        if (alive) setError(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const groups = useMemo(() => groupByDay(runs ?? []), [runs]);

  if (error) return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.notAvailable')}</p>;
  if (runs == null) {
    return (
      <div className="flex items-center gap-2 px-1 py-3 text-[12px] text-muted-foreground/60">
        <Loader2 size={13} className="animate-spin" /> {t('common.loading')}
      </div>
    );
  }
  if (runs.length === 0) return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5 px-0.5 text-[11px] text-muted-foreground/70">
        <History size={13} /> {t('workspace.runHistory')}
      </div>
      {groups.map(([day, dayRuns]) => (
        <div key={day} className="space-y-0.5">
          <div className="px-0.5 text-[10px] uppercase tracking-wide text-muted-foreground/40">{day}</div>
          {dayRuns.map((run) => (
            <button
              key={run.id}
              type="button"
              onClick={() => onOpenRun(run.id)}
              aria-current={run.id === activeRunId ? 'true' : undefined}
              className={cn(
                'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12px]',
                run.id === activeRunId ? 'bg-primary/[0.08]' : 'hover:bg-accent/40',
              )}
              title={run.id}
            >
              <span className="min-w-0 flex-1 truncate text-foreground/85">
                {firstLine((run as { input?: { query?: string } }).input?.query) ?? run.id}
              </span>
              <span className={cn('shrink-0 text-[10px]', statusClass(run.status))}>{run.status}</span>
              <ChevronRight size={11} className="shrink-0 text-muted-foreground/30" />
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

function firstLine(text: string | undefined): string | undefined {
  if (!text) return undefined;
  const line = text.split('\n')[0].trim();
  return line.length > 80 ? `${line.slice(0, 80)}…` : line || undefined;
}

function groupByDay(runs: WorkspaceRunRow[]): Array<[string, WorkspaceRunRow[]]> {
  const map = new Map<string, WorkspaceRunRow[]>();
  for (const run of runs) {
    const stamp = run.finishedAt ?? run.updatedAt ?? run.createdAt;
    const day = stamp ? new Date(stamp).toLocaleDateString() : '—';
    const list = map.get(day) ?? [];
    list.push(run);
    map.set(day, list);
  }
  return [...map.entries()];
}
