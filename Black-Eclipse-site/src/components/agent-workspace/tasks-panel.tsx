'use client';

// ── Agent Workspace — Plan / Tasks panel ──────────────────────────────────────
// The agent's plan as a checklist. Statuses are shown with an icon + a text
// label (never color alone). No private reasoning is exposed — only task titles
// the runtime itself surfaced.

import { Check, CircleDashed, Loader2, CircleSlash, ListChecks, XCircle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { AgentTask, TaskStatus } from '@/lib/agent-workspace/types';

const STATUS_KEY: Record<TaskStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  skipped: 'Skipped',
  blocked: 'Blocked',
};

function TaskIcon({ status }: { status: TaskStatus }) {
  switch (status) {
    case 'completed':
      return <Check size={13} className="text-emerald-400" />;
    case 'running':
      return <Loader2 size={13} className="animate-spin text-primary" />;
    case 'failed':
      return <XCircle size={13} className="text-rose-400" />;
    case 'skipped':
      return <CircleSlash size={13} className="text-muted-foreground/50" />;
    case 'blocked':
      return <CircleDashed size={13} className="text-amber-400" />;
    default:
      return <CircleDashed size={13} className="text-muted-foreground/40" />;
  }
}

export function TasksPanel({ tasks }: { tasks: AgentTask[] }) {
  const t = useT();
  if (tasks.length === 0) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }
  const done = tasks.filter((x) => x.status === 'completed').length;
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 px-0.5 text-[11px] text-muted-foreground/60">
        <ListChecks size={13} />
        <span className="tabular-nums">{done}/{tasks.length}</span>
      </div>
      <ol className="space-y-0.5">
        {tasks.map((task) => (
          <li
            key={task.id}
            className={cn(
              'flex items-start gap-2 rounded-lg px-2 py-1.5',
              task.status === 'running' && 'bg-primary/[0.06]',
            )}
          >
            <span className="mt-0.5 shrink-0">
              <TaskIcon status={task.status} />
            </span>
            <span
              className={cn(
                'min-w-0 flex-1 text-[12px]',
                task.status === 'completed' && 'text-muted-foreground',
                task.status === 'pending' && 'text-muted-foreground/60',
                task.status === 'running' && 'text-foreground',
                task.status === 'failed' && 'text-rose-200',
                task.status === 'blocked' && 'text-amber-200',
              )}
            >
              {task.title}
            </span>
            <span className="shrink-0 text-[9.5px] uppercase tracking-wide text-muted-foreground/40">{STATUS_KEY[task.status]}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
