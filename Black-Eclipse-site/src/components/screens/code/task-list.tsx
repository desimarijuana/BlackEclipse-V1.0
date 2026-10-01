'use client';

// ── Code tasks — the task list (Phase 5) ────────────────────────────────────
// One row per task: a plain status, a plain progress line, and the autonomy
// choice as a plain sentence. The mechanism (workspace, checks, argv) is never
// on this surface; it lives behind "details" and in the trace.

import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import { cn } from '@/lib/utils';
import type { CodeTask, TaskStatus } from '@/lib/harness/code-browser';

const STATUS_KEY: Record<TaskStatus, TranslationKey> = {
  created: 'code.task.status.created',
  plan_review: 'code.task.status.planReview',
  completed: 'code.task.status.completed',
  failed: 'code.task.status.failed',
  cancelled: 'code.task.status.cancelled',
  discarded: 'code.task.status.discarded',
};

const AUTONOMY_KEY: Record<string, TranslationKey> = {
  plan_only: 'code.task.badge.planOnly',
  edit_verify: 'code.task.badge.editVerify',
  approve_external: 'code.task.badge.approveExternal',
};

export interface TaskListProps {
  tasks: CodeTask[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

export function TaskList({ tasks, selectedId, onSelect }: TaskListProps) {
  const t = useT();
  if (tasks.length === 0) {
    return <div className="glass-card-subtle rounded-xl p-3 text-[12px] text-muted-foreground">{t('code.task.empty')}</div>;
  }
  return (
    <ul className="space-y-1.5">
      {tasks.map((task) => (
        <li key={task.id}>
          <button
            type="button"
            onClick={() => onSelect?.(task.id)}
            className={cn(
              'glass-card-subtle flex w-full items-center gap-2 rounded-xl border border-border/40 p-2.5 text-left text-[12px] transition-colors',
              selectedId === task.id && 'border-primary/50',
            )}
          >
            <span className="min-w-0 flex-1 truncate text-foreground">{task.query || t('code.task.title')}</span>
            <span className="shrink-0 text-muted-foreground/70">
              {t(AUTONOMY_KEY[task.autonomy] ?? 'code.task.badge.planOnly')}
            </span>
            <span className="shrink-0 text-muted-foreground">{t(STATUS_KEY[task.status] ?? 'code.task.status.created')}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
