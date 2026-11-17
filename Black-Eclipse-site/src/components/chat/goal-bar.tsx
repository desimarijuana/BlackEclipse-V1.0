'use client';

// ── GoalBar — the W4 autonomy status strip ───────────────────────────────────
// A compact, read-mostly surface over /api/goals and /api/loops. It shows every
// active goal (not just the newest) with its turn count, gate status, phase
// (queued/running), last verdict and live run, plus the newest loop/heartbeat.
// It owns no scheduling or agent logic: every action calls the front door, and
// the Python runtime remains authoritative. While something is running it polls
// at 5s; idle it backs off to 30s so a chat surface is not a busy loop.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  cancelGoal,
  cancelLoop,
  extendGoal,
  getHealth,
  goalVerdictHistory,
  listGoals,
  listLoops,
  pauseGoal,
  pauseLoop,
  reevaluateGoal,
  resumeGoal,
  resumeLoop,
  type AutonomyHealth,
  type GoalView,
  type GoalVerdictView,
  type LoopView,
} from '@/lib/harness/clients/autonomy-browser';
import { useT } from '@/lib/i18n/use-t';
import { cn } from '@/lib/utils';

interface GoalBarProps {
  sessionId?: string | null;
  className?: string;
}

function statusTone(status: string): string {
  if (status === 'active') return 'text-emerald-400';
  if (status === 'paused') return 'text-amber-400';
  if (status === 'blocked') return 'text-rose-400';
  return 'text-muted-foreground';
}

const button =
  'rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition hover:text-foreground disabled:opacity-40';
const OPEN_STATUSES = ['active', 'paused', 'blocked'];

export function GoalBar({ sessionId, className }: GoalBarProps) {
  const t = useT();
  const [goals, setGoals] = useState<GoalView[]>([]);
  const [loops, setLoops] = useState<LoopView[]>([]);
  const [health, setHealth] = useState<AutonomyHealth | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [openGoalId, setOpenGoalId] = useState<string | null>(null);
  const [verdicts, setVerdicts] = useState<GoalVerdictView[] | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextGoals, nextLoops, nextHealth] = await Promise.all([
        listGoals(sessionId ? { sessionId } : {}),
        listLoops(sessionId ? { sessionId } : {}),
        getHealth().catch(() => null),
      ]);
      setGoals(nextGoals);
      setLoops(nextLoops);
      if (nextHealth) setHealth(nextHealth);
      setFailed(false);
    } catch {
      // The runtime may be starting or absent; the bar is optional, so it stays
      // silent rather than turning a chat surface into an error page.
      setFailed(true);
    }
  }, [sessionId]);

  const activeGoals = useMemo(
    () => goals.filter((item) => OPEN_STATUSES.includes(item.status)).slice(0, 3),
    [goals],
  );
  const loop = useMemo(
    () => loops.find((item) => item.status === 'active' || item.status === 'paused'),
    [loops],
  );
  const hasActive = Boolean(
    activeGoals.some((item) =>
      item.status === 'active' && item.taskStatus !== 'TODO',
    ) || loop?.status === 'active',
  );

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const run = async () => {
      if (typeof document === 'undefined' || document.visibilityState !== 'hidden') {
        await refresh();
      }
      if (!cancelled) timer = window.setTimeout(run, hasActive ? 5_000 : 30_000);
    };
    void run();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [refresh, hasActive]);

  if (failed) return null;
  if (!activeGoals.length && !loop && health?.mode === 'off') {
    // Nothing running, but the engine is off: say so once instead of silently
    // letting `/goal` fail later.
    return (
      <div
        className={cn(
          'mb-2 flex items-center gap-2 rounded-2xl border border-amber-400/20 glass-card px-3 py-2 text-[11px] text-amber-300/90',
          className,
        )}
        data-nodrag
      >
        <span className="font-semibold">{t('autonomy.loopOff')}</span>
        <span className="truncate" title={t('autonomy.loopOffHint')}>
          {t('autonomy.loopOffHint')}
        </span>
      </div>
    );
  }
  if (!activeGoals.length && !loop) return null;

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

  async function toggleDetails(id: string) {
    if (openGoalId === id) {
      setOpenGoalId(null);
      setVerdicts(null);
      return;
    }
    setOpenGoalId(id);
    setVerdicts(null);
    setBusy(`details:${id}`);
    try {
      setVerdicts(await goalVerdictHistory(id));
    } catch {
      setVerdicts([]);
    } finally {
      setBusy(null);
    }
  }

  function phaseOf(item: GoalView): string {
    if (item.status !== 'active') return item.status;
    if (item.taskStatus === 'TODO') return t('autonomy.queued');
    if (item.taskStatus === 'IN_PROGRESS' || item.taskStatus === 'VERIFYING') {
      return t('autonomy.inProgress');
    }
    return item.status;
  }

  function gateLabel(item: GoalView): string {
    const results = item.lastVerdict?.gateResults ?? [];
    if (!results.length) {
      return item.gates.length ? t('autonomy.gatesPending') : t('autonomy.judgeOnly');
    }
    const failed = results.filter((gate) => !gate.ok);
    if (failed.length) return t('autonomy.gateFailing', { check: failed[0].check });
    return t('autonomy.gatesPassing', { count: results.length });
  }

  return (
    <div
      className={cn(
        'mb-2 flex flex-col gap-2 rounded-2xl border border-white/10 glass-card px-3 py-2 text-[11px] text-muted-foreground',
        className,
      )}
      data-nodrag
    >
      {activeGoals.map((goal) => {
        const capped = goal.usedTurns >= goal.maxTurns;
        const open = openGoalId === goal.id;
        return (
          <div key={goal.id} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="font-semibold text-foreground/90">{t('autonomy.goal')}</span>
              <span className={cn('font-medium', statusTone(goal.status))}>
                {phaseOf(goal)}
              </span>
              <span className="truncate max-w-[240px]" title={goal.objective}>{goal.objective}</span>
              <span>{t('autonomy.turn', { used: goal.usedTurns, max: goal.maxTurns })}</span>
              <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px]">
                {gateLabel(goal)}
              </span>
              {goal.lastVerdict?.reason ? (
                <span className="truncate max-w-[280px]" title={goal.lastVerdict.reason}>
                  {goal.lastVerdict.verdict}: {goal.lastVerdict.reason}
                </span>
              ) : null}
              {goal.nextRunAt ? (
                <span>{t('autonomy.wakes', { time: goal.nextRunAt.slice(11, 16) })}</span>
              ) : null}
              {goal.currentRunId ? (
                <span className="truncate max-w-[140px]" title={goal.currentRunId}>
                  {t('autonomy.running', { run: goal.currentRunId.slice(0, 10) })}
                </span>
              ) : null}
              <span className="ml-auto flex items-center gap-1">
                {goal.status === 'active' ? (
                  <button
                    type="button"
                    className={button}
                    disabled={busy !== null}
                    onClick={() => void act('goal-pause', () => pauseGoal(goal.id, 'goal bar'))}
                  >
                    {t('autonomy.pause')}
                  </button>
                ) : null}
                {goal.status === 'paused' || goal.status === 'blocked' ? (
                  <button
                    type="button"
                    className={button}
                    disabled={busy !== null}
                    onClick={() => void act('goal-resume', () => resumeGoal(goal.id))}
                    title={capped ? t('autonomy.extend') : undefined}
                  >
                    {t('autonomy.resume')}
                  </button>
                ) : null}
                {goal.status === 'blocked' ? (
                  <button
                    type="button"
                    className={button}
                    disabled={busy !== null}
                    onClick={() => void act('goal-reevaluate', () => reevaluateGoal(goal.id))}
                  >
                    {t('autonomy.reevaluate')}
                  </button>
                ) : null}
                {capped && goal.status !== 'cancelled' && goal.status !== 'completed' ? (
                  <button
                    type="button"
                    className={button}
                    disabled={busy !== null}
                    onClick={() => void act('goal-extend', () => extendGoal(goal.id, 5))}
                  >
                    {t('autonomy.extend')}
                  </button>
                ) : null}
                <button
                  type="button"
                  className={button}
                  disabled={busy !== null}
                  onClick={() => void toggleDetails(goal.id)}
                >
                  {t('autonomy.details')}
                </button>
                {goal.status !== 'cancelled' && goal.status !== 'completed' ? (
                  <button
                    type="button"
                    className={button}
                    disabled={busy !== null}
                    onClick={() => void act('goal-cancel', () => cancelGoal(goal.id))}
                  >
                    {t('autonomy.cancel')}
                  </button>
                ) : null}
              </span>
            </div>

            {open ? (
              <div className="flex flex-col gap-1 border-t border-white/5 pt-1">
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {goal.gates.length ? (
                    goal.gates.map((gate) => (
                      <span key={gate.id} className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px]">
                        {gate.check}
                      </span>
                    ))
                  ) : (
                    <span>{t('autonomy.judgeOnly')}</span>
                  )}
                  {goal.workspaceId ? <span>workspace {goal.workspaceId}</span> : null}
                  {goal.currentRunId ? <span>run {goal.currentRunId}</span> : null}
                </div>
                {verdicts === null ? (
                  <span>{t('autonomy.loading')}</span>
                ) : verdicts.length ? (
                  verdicts.slice(0, 5).map((item) => (
                    <div key={`${item.turn}-${item.createdAt ?? ''}`} className="flex items-center gap-2">
                      <span className="shrink-0">turn {item.turn}</span>
                      <span className={cn('shrink-0 font-medium', statusTone(item.verdict === 'done' ? 'completed' : item.verdict))}>
                        {item.verdict}
                      </span>
                      <span className="truncate max-w-[420px]" title={item.reason}>
                        {item.reason}
                      </span>
                    </div>
                  ))
                ) : (
                  <span>{t('autonomy.noneYet')}</span>
                )}
              </div>
            ) : null}
          </div>
        );
      })}

      {loop ? (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-white/5 pt-1">
          <span className="font-semibold text-foreground/90">
            {loop.kind === 'heartbeat' ? t('autonomy.heartbeat') : t('autonomy.loop')}
          </span>
          <span className={cn('font-medium', statusTone(loop.status))}>{loop.status}</span>
          <span>{t('autonomy.every', { minutes: Math.round(loop.intervalSeconds / 60) || 1 })}</span>
          <span>{t('autonomy.tick', { used: loop.usedTicks, max: loop.maxTicks })}</span>
          {loop.nextTickAt ? (
            <span>{t('autonomy.next', { time: loop.nextTickAt.slice(11, 16) })}</span>
          ) : null}
          <span className="truncate max-w-[240px]" title={loop.prompt}>{loop.prompt}</span>
          <span className="ml-auto flex items-center gap-1">
            {loop.status === 'active' ? (
              <button
                type="button"
                className={button}
                disabled={busy !== null}
                onClick={() => void act('loop-pause', () => pauseLoop(loop.id, 'goal bar'))}
              >
                {t('autonomy.pause')}
              </button>
            ) : null}
            {loop.status === 'paused' ? (
              <button
                type="button"
                className={button}
                disabled={busy !== null}
                onClick={() => void act('loop-resume', () => resumeLoop(loop.id))}
              >
                {t('autonomy.resume')}
              </button>
            ) : null}
            <button
              type="button"
              className={button}
              disabled={busy !== null}
              onClick={() => void act('loop-cancel', () => cancelLoop(loop.id))}
            >
              {t('autonomy.cancel')}
            </button>
          </span>
        </div>
      ) : null}
    </div>
  );
}
