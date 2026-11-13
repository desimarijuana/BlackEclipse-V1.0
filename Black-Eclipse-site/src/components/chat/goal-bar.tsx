'use client';

// ── GoalBar — the W4 autonomy status strip ───────────────────────────────────
// A compact, read-mostly surface over /api/goals and /api/loops. It shows the
// newest goal (turns, gate status, last verdict) and the newest loop/heartbeat,
// with pause/resume/cancel. It owns no scheduling or agent logic: every action
// calls the front door, and the Python runtime remains authoritative.

import { useCallback, useEffect, useState } from 'react';
import {
  cancelGoal,
  cancelLoop,
  listGoals,
  listLoops,
  pauseGoal,
  pauseLoop,
  resumeGoal,
  resumeLoop,
  type GoalView,
  type LoopView,
} from '@/lib/harness/clients/autonomy-client';
import { cn } from '@/lib/utils';

interface GoalBarProps {
  sessionId?: string | null;
  className?: string;
}

function gateLabel(goal: GoalView): string {
  const results = goal.lastVerdict?.gateResults ?? [];
  if (!results.length) return goal.gates.length ? 'gates pending' : 'judge only';
  const failed = results.filter((item) => !item.ok);
  if (failed.length) return `${failed[0].check} failing`;
  return `${results.length} gate${results.length === 1 ? '' : 's'} passing`;
}

function statusTone(status: string): string {
  if (status === 'active') return 'text-emerald-400';
  if (status === 'paused') return 'text-amber-400';
  if (status === 'blocked') return 'text-rose-400';
  return 'text-muted-foreground';
}

export function GoalBar({ sessionId, className }: GoalBarProps) {
  const [goals, setGoals] = useState<GoalView[]>([]);
  const [loops, setLoops] = useState<LoopView[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [nextGoals, nextLoops] = await Promise.all([
        listGoals(sessionId ? { sessionId } : {}),
        listLoops(sessionId ? { sessionId } : {}),
      ]);
      setGoals(nextGoals);
      setLoops(nextLoops);
      setFailed(false);
    } catch {
      // The runtime may be starting or absent; the bar is optional, so it stays
      // silent rather than turning a chat surface into an error page.
      setFailed(true);
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      // A hidden tab does not need to poll the runtime.
      if (typeof document === 'undefined' || document.visibilityState !== 'hidden') {
        void refresh();
      }
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const goal = goals.find((item) =>
    ['active', 'paused', 'blocked'].includes(item.status),
  );
  const loop = loops.find((item) => item.status === 'active' || item.status === 'paused');

  if (failed || (!goal && !loop)) return null;

  const goalTone = goal ? statusTone(goal.status) : '';
  const loopTone = loop ? statusTone(loop.status) : '';

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    try {
      await fn();
      await refresh();
    } catch {
      // The command/route reports its own error; the bar only refreshes.
    } finally {
      setBusy(null);
    }
  }

  const button = 'rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition hover:text-foreground disabled:opacity-40';

  return (
    <div
      className={cn(
        'mb-2 flex flex-col gap-1 rounded-2xl border border-white/10 glass-card px-3 py-2 text-[11px] text-muted-foreground',
        className,
      )}
      data-nodrag
    >
      {goal ? (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-semibold text-foreground/90">Goal</span>
          <span className={cn('font-medium', goalTone)}>{goal.status}</span>
          <span className="truncate max-w-[240px]" title={goal.objective}>{goal.objective}</span>
          <span>turn {goal.usedTurns}/{goal.maxTurns}</span>
          <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px]">
            {gateLabel(goal)}
          </span>
          {goal.lastVerdict?.reason ? (
            <span className="truncate max-w-[280px]" title={goal.lastVerdict.reason}>
              {goal.lastVerdict.verdict}: {goal.lastVerdict.reason}
            </span>
          ) : null}
          {goal.nextRunAt ? (
            <span>wakes {goal.nextRunAt.slice(11, 16)}Z</span>
          ) : null}
          <span className="ml-auto flex items-center gap-1">
            {goal.status === 'active' ? (
              <button
                type="button"
                className={button}
                disabled={busy !== null}
                onClick={() => void act('goal-pause', () => pauseGoal(goal.id, 'goal bar'))}
              >
                Pause
              </button>
            ) : null}
            {goal.status === 'paused' || goal.status === 'blocked' ? (
              <button
                type="button"
                className={button}
                disabled={busy !== null}
                onClick={() => void act('goal-resume', () => resumeGoal(goal.id))}
              >
                Resume
              </button>
            ) : null}
            {goal.status !== 'cancelled' && goal.status !== 'completed' ? (
              <button
                type="button"
                className={button}
                disabled={busy !== null}
                onClick={() => void act('goal-cancel', () => cancelGoal(goal.id))}
              >
                Cancel
              </button>
            ) : null}
          </span>
        </div>
      ) : null}

      {loop ? (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-semibold text-foreground/90">
            {loop.kind === 'heartbeat' ? 'Heartbeat' : 'Loop'}
          </span>
          <span className={cn('font-medium', loopTone)}>{loop.status}</span>
          <span>every {Math.round(loop.intervalSeconds / 60) || 1}m</span>
          <span>tick {loop.usedTicks}/{loop.maxTicks}</span>
          {loop.nextTickAt ? <span>next {loop.nextTickAt.slice(11, 16)}Z</span> : null}
          <span className="truncate max-w-[240px]" title={loop.prompt}>{loop.prompt}</span>
          <span className="ml-auto flex items-center gap-1">
            {loop.status === 'active' ? (
              <button
                type="button"
                className={button}
                disabled={busy !== null}
                onClick={() => void act('loop-pause', () => pauseLoop(loop.id, 'goal bar'))}
              >
                Pause
              </button>
            ) : null}
            {loop.status === 'paused' ? (
              <button
                type="button"
                className={button}
                disabled={busy !== null}
                onClick={() => void act('loop-resume', () => resumeLoop(loop.id))}
              >
                Resume
              </button>
            ) : null}
            <button
              type="button"
              className={button}
              disabled={busy !== null}
              onClick={() => void act('loop-cancel', () => cancelLoop(loop.id))}
            >
              Cancel
            </button>
          </span>
        </div>
      ) : null}
    </div>
  );
}
