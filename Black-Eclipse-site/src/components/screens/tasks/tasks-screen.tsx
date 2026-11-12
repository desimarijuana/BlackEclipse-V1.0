'use client';

// ── The Tasks screen ─────────────────────────────────────────────────────────
// Shows the durable Task / Plan tree from the real runtime: status, priority,
// progress, dependencies, blocked/waiting reasons, retry counts, criteria and
// executions. Every value comes from `/api/plans` + `/api/tasks` (the Python
// Task / Plan store) — nothing here is invented. Actions route through the same
// state machine the agent uses, so completion is verified, not asserted.

import { useCallback, useEffect, useState } from 'react';
import { useActiveInterval } from '@/hooks/use-active-interval';
import { cn } from '@/lib/utils';
import {
  blockTask,
  cancelTask,
  completeTask,
  createPlan,
  createTask,
  getPlan,
  listPlans,
  removeDependency,
  retryTask,
  setCriterion,
  startPlan,
  unblockTask,
  type Plan,
  type PlanView,
  type TaskNode,
} from '@/lib/harness/clients/tasks-browser';

const STATUS_MARK: Record<string, string> = {
  TODO: '○', IN_PROGRESS: '●', BLOCKED: '⛔', WAITING: '…',
  FAILED: '✗', COMPLETED: '✓', CANCELLED: '⊘',
};

const STATUS_TONE: Record<string, string> = {
  TODO: 'text-muted-foreground',
  IN_PROGRESS: 'text-sky-400',
  BLOCKED: 'text-amber-400',
  WAITING: 'text-amber-300',
  FAILED: 'text-rose-400',
  COMPLETED: 'text-emerald-400',
  CANCELLED: 'text-muted-foreground',
};

function statusLine(task: TaskNode): string | null {
  if (task.status === 'BLOCKED' && task.blockedBy.length) {
    return `Blocked by ${task.blockedBy.slice(0, 3).join(', ')}`;
  }
  if (task.status === 'WAITING' && task.waitingReason) {
    return `Waiting for ${task.waitingReason.replace(/_/g, ' ').toLowerCase()}`;
  }
  if (task.status === 'FAILED' && task.error) return task.error;
  return null;
}

export function TasksScreen({ active = true }: { active?: boolean }) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<PlanView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newPlanName, setNewPlanName] = useState('');

  const refreshPlans = useCallback(async () => {
    try {
      const next = await listPlans();
      setPlans(next);
      setError(null);
      setSelected((prev) => prev ?? next[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'could not load plans');
    }
  }, []);

  const refreshView = useCallback(async (planId: string | null) => {
    if (!planId) {
      setView(null);
      return;
    }
    try {
      setView(await getPlan(planId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'could not load plan');
    }
  }, []);

  useEffect(() => {
    void refreshPlans();
  }, [refreshPlans]);

  useEffect(() => {
    void refreshView(selected);
  }, [selected, refreshView]);
  useActiveInterval(active, () => void refreshView(selected), 5000);

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn();
        await refreshView(selected);
        await refreshPlans();
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'action failed');
      } finally {
        setBusy(false);
      }
    },
    [selected, refreshView, refreshPlans],
  );

  const onCreatePlan = () =>
    run(async () => {
      const name = newPlanName.trim();
      if (!name) return;
      const plan = await createPlan({ name, objective: name });
      setNewPlanName('');
      setSelected(plan.id);
    });

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Tasks</h1>
          <p className="text-sm text-muted-foreground">
            Durable plans and steps. A step completes only when its dependencies,
            subtasks and acceptance criteria are met.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={newPlanName}
            onChange={(e) => setNewPlanName(e.target.value)}
            placeholder="New plan name"
            className="glass-card-subtle rounded-md px-3 py-1.5 text-sm outline-none"
          />
          <button
            type="button"
            onClick={onCreatePlan}
            disabled={busy || !newPlanName.trim()}
            className="glass-card-subtle rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            Create plan
          </button>
        </div>
      </header>

      {error && (
        <div className="glass-card-subtle mb-4 rounded-md border border-rose-500/30 px-3 py-2 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[18rem_1fr]">
        <aside className="glass-card rounded-lg p-3">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Plans
          </h2>
          {plans.length === 0 ? (
            <p className="text-sm text-muted-foreground">No plans yet.</p>
          ) : (
            <ul className="space-y-1">
              {plans.map((plan) => (
                <li key={plan.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(plan.id)}
                    className={cn(
                      'w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                      plan.id === selected ? 'glass-card-strong' : 'hover:bg-white/5',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate">{plan.name}</span>
                      <span className="text-[10px] uppercase text-muted-foreground">
                        {plan.status}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="glass-card min-h-[24rem] rounded-lg p-4">
          {!view ? (
            <p className="text-sm text-muted-foreground">Select a plan to see its steps.</p>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">{view.plan.name}</h2>
                  <p className="text-xs text-muted-foreground">
                    {view.stats.total} tasks · {view.stats.progress}% ·{' '}
                    {view.stats.runnable} ready · {Object.entries(view.stats.byStatus)
                      .map(([k, v]) => `${v} ${k.toLowerCase()}`)
                      .join(', ')}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => run(() => startPlan(view.plan.id))}
                  disabled={busy || view.plan.status === 'RUNNING'}
                  className="glass-card-subtle rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  {view.plan.status === 'RUNNING' ? 'Running' : 'Start plan'}
                </button>
              </div>

              <div className="space-y-2">
                {view.tasks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">This plan has no steps yet.</p>
                ) : (
                  view.tasks.map((task) => (
                    <TaskRow key={task.id} task={task} depth={0} busy={busy} run={run} />
                  ))
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function TaskRow({
  task,
  depth,
  busy,
  run,
}: {
  task: TaskNode;
  depth: number;
  busy: boolean;
  run: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [open, setOpen] = useState(depth === 0);
  const note = statusLine(task);
  const criteria = task.criteria ?? [];
  const deps = task.dependencies ?? [];

  return (
    <div>
      <div
        className="rounded-md px-2 py-2"
        style={{ marginLeft: depth * 16 }}
      >
        <div className="flex items-start justify-between gap-2">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-start gap-2 text-left"
          >
            <span className={cn('mt-[1px] text-sm', STATUS_TONE[task.status])}>
              {STATUS_MARK[task.status] ?? '·'}
            </span>
            <span>
              <span className="text-sm font-medium">{task.title}</span>
              <span className="ml-2 text-[10px] uppercase text-muted-foreground">
                {task.priority} · {task.status}
                {task.retryCount > 0 ? ` · ${task.retryCount} retries` : ''}
                {task.executionCount ? ` · ${task.executionCount} runs` : ''}
              </span>
              {note && (
                <span className="mt-0.5 block text-xs text-amber-300/90">{note}</span>
              )}
            </span>
          </button>

          <div className="flex shrink-0 items-center gap-2">
            <div className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-white/10 sm:block">
              <div
                className="h-full rounded-full bg-emerald-400/70"
                style={{ width: `${task.progress}%` }}
              />
            </div>
            <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">
              {task.progress}%
            </span>
          </div>
        </div>

        {open && (
          <div className="mt-2 ml-6 space-y-2">
            {criteria.length > 0 && (
              <ul className="space-y-1">
                {criteria.map((c) => (
                  <li key={c.id} className="flex items-center gap-2 text-xs">
                    <span
                      className={cn(
                        c.state === 'PASSED'
                          ? 'text-emerald-400'
                          : c.state === 'FAILED'
                            ? 'text-rose-400'
                            : 'text-muted-foreground',
                      )}
                    >
                      {c.state === 'PASSED' ? '✓' : c.state === 'FAILED' ? '✗' : '○'}
                    </span>
                    <span className="text-muted-foreground">{c.text}</span>
                    {c.state === 'PENDING' && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => run(() => setCriterion(c.id, 'PASSED'))}
                        className="rounded px-1.5 py-0.5 text-[10px] hover:bg-white/10 disabled:opacity-50"
                      >
                        Mark passed
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {deps.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {deps.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    disabled={busy}
                    title="Remove dependency"
                    onClick={() => run(() => removeDependency(task.id, d.dependsOnTaskId))}
                    className="glass-card-subtle rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                  >
                    needs {d.dependsOnTaskId.slice(0, 10)}…
                  </button>
                ))}
              </div>
            )}

            {!task.children.length && (
              <TaskActions task={task} busy={busy} run={run} />
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(() =>
                  createTask({
                    title: 'New step',
                    planId: task.planId ?? undefined,
                    parentTaskId: task.id,
                  }),
                )
              }
              className="rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-white/10 disabled:opacity-50"
            >
              + subtask
            </button>
          </div>
        )}
      </div>

      {task.children.map((child) => (
        <TaskRow key={child.id} task={child} depth={depth + 1} busy={busy} run={run} />
      ))}
    </div>
  );
}

function TaskActions({
  task,
  busy,
  run,
}: {
  task: TaskNode;
  busy: boolean;
  run: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const base = 'rounded px-2 py-0.5 text-[11px] disabled:opacity-50 hover:bg-white/10';
  const terminal = task.status === 'COMPLETED' || task.status === 'CANCELLED';
  return (
    <div className="flex flex-wrap gap-1">
      {!terminal && task.status !== 'FAILED' && (
        <button
          type="button"
          className={base}
          disabled={busy}
          onClick={() => run(() => completeTask(task.id))}
        >
          Complete
        </button>
      )}
      {(task.status === 'FAILED' || task.status === 'BLOCKED' || task.status === 'WAITING') && (
        <button
          type="button"
          className={base}
          disabled={busy}
          onClick={() => run(() => retryTask(task.id))}
        >
          Retry
        </button>
      )}
      {task.status === 'BLOCKED' && (
        <button
          type="button"
          className={base}
          disabled={busy}
          onClick={() => run(() => unblockTask(task.id))}
        >
          Unblock
        </button>
      )}
      {!terminal && (
        <button
          type="button"
          className={base}
          disabled={busy}
          onClick={() => run(() => blockTask(task.id))}
        >
          Block
        </button>
      )}
      {!terminal && (
        <button
          type="button"
          className={base}
          disabled={busy}
          onClick={() => run(() => cancelTask(task.id))}
        >
          Cancel
        </button>
      )}
    </div>
  );
}
