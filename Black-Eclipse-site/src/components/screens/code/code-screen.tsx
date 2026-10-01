'use client';

// ── Code tasks — the shell container (Phase 5 surface, mounted Phase 12.5) ────
// The seven code panels were built in Phase 5 but nothing mounted them, so no
// user could reach them. This is the thin container that wires them to the
// EXISTING code-client (which proxies the existing /code routes) and renders them
// through the shell's keep-alive tab. It holds NO agentic logic: it fetches,
// passes props, and shows what the runtime recorded — the same division the jobs
// screen uses. Every string is an i18n key.

import { useCallback, useEffect, useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import { useSubroute } from '@/hooks/use-subroute';
import { cn } from '@/lib/utils';
import {
  acceptCodePlan,
  cancelCodeTask,
  decideCodeApproval,
  discardCodeTask,
  getCodeTask,
  getCodeTaskDiff,
  listCodeApprovals,
  listCodeTasks,
  resumeCodeTask,
  type CodeApproval,
  type CodeTask,
  type CodeTaskDiff,
} from '@/lib/harness/code-browser';
import { TaskList } from './task-list';
import { TaskDetail } from './task-detail';
import { CodeApprovals } from './code-approvals';

type CodeView = 'tasks' | 'approvals';

export function CodeScreen() {
  const t = useT();
  const [tasks, setTasks] = useState<CodeTask[]>([]);
  const [approvals, setApprovals] = useState<CodeApproval[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CodeTask | null>(null);
  const [diff, setDiff] = useState<CodeTaskDiff | null>(null);
  const [view, setView] = useState<CodeView>('tasks');
  const [error, setError] = useState<string | null>(null);

  // A `code.approvals` palette request brings the "waiting for you" panel forward;
  // `code.tasks` returns to the list. Both panels stay mounted either way.
  useSubroute('code', (req) => {
    setView(req.subroute.split('.')[1] === 'approvals' ? 'approvals' : 'tasks');
  });

  const refresh = useCallback(async () => {
    try {
      const [nextTasks, nextApprovals] = await Promise.all([listCodeTasks(), listCodeApprovals()]);
      setTasks(nextTasks);
      setApprovals(nextApprovals);
      setError(null);
    } catch {
      setError(t('code.task.loadFailed'));
    }
  }, [t]);

  useEffect(() => { void refresh(); }, [refresh]);

  // Load the selected task's detail + its change (the diff is optional: a task
  // with no bound work area simply has none).
  useEffect(() => {
    if (!selectedId) { setDetail(null); setDiff(null); return; }
    let alive = true;
    void (async () => {
      try {
        const [task, change] = await Promise.all([getCodeTask(selectedId), getCodeTaskDiff(selectedId)]);
        if (alive) { setDetail(task); setDiff(change); }
      } catch {
        if (alive) { setDetail(null); setDiff(null); }
      }
    })();
    return () => { alive = false; };
  }, [selectedId, tasks]);

  const after = useCallback(async () => { await refresh(); }, [refresh]);

  return (
    <div className="space-y-3 p-4">
      <header className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-medium text-foreground">{t('code.task.heading')}</h2>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <button
            type="button"
            onClick={() => setView('tasks')}
            className={cn('glass-card-subtle rounded-lg px-2.5 py-1 text-[11px] transition-colors',
              view === 'tasks' ? 'border border-primary/50 text-foreground' : 'text-muted-foreground')}
          >
            {t('code.task.listHeading')}
          </button>
          <button
            type="button"
            onClick={() => setView('approvals')}
            className={cn('glass-card-subtle rounded-lg px-2.5 py-1 text-[11px] transition-colors',
              view === 'approvals' ? 'border border-primary/50 text-foreground' : 'text-muted-foreground')}
          >
            {t('code.approvals.title')}
          </button>
          <button
            type="button"
            onClick={() => { void refresh(); }}
            className="glass-button rounded-lg px-3 py-1.5 text-[12px] text-foreground"
          >
            {t('code.task.reload')}
          </button>
        </div>
      </header>

      {error && (
        <div className="glass-card-subtle rounded-xl border border-red-500/30 p-2.5 text-[12px] text-red-300">
          {error}
        </div>
      )}

      <div className={cn('grid gap-3 lg:grid-cols-2', view !== 'tasks' && 'hidden')}>
        <TaskList tasks={tasks} selectedId={selectedId} onSelect={setSelectedId} />
        {detail ? (
          <TaskDetail
            task={detail}
            diffFiles={diff ? [...diff.added, ...diff.modified, ...diff.deleted] : []}
            diffUnified={diff?.unified}
            diffDigest={diff?.digest ?? null}
            onAcceptPlan={() => {
              if (!detail.plan) return;
              void acceptCodePlan(detail.id, detail.plan.steps, detail.plan.checkClasses).then(after);
            }}
            onRejectPlan={() => setSelectedId(null)}
            onResume={() => { void resumeCodeTask(detail.id).then(after); }}
            onCancel={() => { void cancelCodeTask(detail.id).then(after); }}
            onDiscard={() => { void discardCodeTask(detail.id).then(() => { setSelectedId(null); return after(); }); }}
          />
        ) : (
          <div className="glass-card-subtle rounded-xl p-3 text-[12px] text-muted-foreground">
            {t('code.task.detailPlaceholder')}
          </div>
        )}
      </div>

      <div className={cn(view !== 'approvals' && 'hidden')}>
        <CodeApprovals
          approvals={approvals}
          onDecide={(id, approve) => { void decideCodeApproval(id, approve).then(after); }}
        />
      </div>
    </div>
  );
}
