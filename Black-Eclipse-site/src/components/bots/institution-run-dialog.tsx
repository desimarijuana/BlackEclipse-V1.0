'use client';

// -- Institution committee runner --------------------------------------------
// Starts the durable analyst -> debate -> trader -> risk -> PM team run and
// renders its live stage timeline, review verdict and final decision memo. It
// adds no orchestration logic: every call goes to the runtime's `/team/*` routes.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Sparkles, Users } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import type { AutomationView } from '@/lib/harness/clients/automation-browser';
import {
  getTeamResult,
  getTeamRun,
  reviewTeam,
  runInstitution,
  type TeamRunStatus,
  type TeamRunView,
  type TeamStatusView,
} from '@/lib/harness/clients/team-client';
import { useSeedInstitutionPack } from '@/lib/bots/institution-bots';

const STAGE_LABELS: Record<string, string> = {
  analysis: 'Analyst',
  bull_case: 'Bull',
  bear_case: 'Bear',
  debate: 'Debate',
  trade_proposal: 'Trader',
  risk_review: 'Risk',
  decision: 'PM',
};

const STAGE_ORDER = ['analysis', 'bull_case', 'bear_case', 'debate', 'trade_proposal', 'risk_review', 'decision'];

const TERMINAL: ReadonlySet<TeamRunStatus> = new Set([
  'COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED',
]);

function stageTone(status: string | undefined): string {
  switch (status) {
    case 'COMPLETED':
      return 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200';
    case 'FAILED':
    case 'CANCELLED':
      return 'border-rose-400/40 bg-rose-400/10 text-rose-200';
    case 'IN_PROGRESS':
    case 'VERIFYING':
    case 'RUNNING':
      return 'border-sky-400/40 bg-sky-400/10 text-sky-200';
    case 'BLOCKED':
    case 'WAITING':
      return 'border-amber-400/40 bg-amber-400/10 text-amber-200';
    default:
      return 'border-border/20 bg-white/5 text-muted-foreground';
  }
}

function statusLabel(status: string | undefined): string {
  if (!status) return 'Pending';
  return status.replace('_', ' ').toLowerCase();
}

export function InstitutionRunDialog({
  open,
  onOpenChange,
  existingBots,
  onSeeded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existingBots: AutomationView[];
  onSeeded: () => void;
}) {
  const { seed, busy: seeding, error: seedErrorBase } = useSeedInstitutionPack();
  const [objective, setObjective] = useState('');
  const [universe, setUniverse] = useState('');
  const [horizon, setHorizon] = useState('');
  const [constraints, setConstraints] = useState('');
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<TeamRunView | null>(null);
  const [status, setStatus] = useState<TeamStatusView | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [reviewOutcome, setReviewOutcome] = useState<string | null>(null);
  const reviewed = useRef(false);

  const reset = useCallback(() => {
    setRun(null);
    setStatus(null);
    setResult(null);
    setReviewOutcome(null);
    setError(null);
    reviewed.current = false;
  }, []);

  useEffect(() => {
    if (!open) {
      reviewed.current = false;
    }
  }, [open]);

  const start = useCallback(async () => {
    if (!objective.trim()) {
      setError('Describe the investment question the committee should decide.');
      return;
    }
    setStarting(true);
    setError(null);
    reset();
    try {
      const created = await runInstitution({
        objective: objective.trim(),
        universe: universe.trim(),
        horizon: horizon.trim(),
        constraints: constraints
          .split(',')
          .map((c) => c.trim())
          .filter(Boolean),
      });
      setRun(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the committee.');
    } finally {
      setStarting(false);
    }
  }, [objective, universe, horizon, constraints, reset]);

  // Poll the durable task graph. One interval, cleared on close/unmount.
  useEffect(() => {
    if (!open || !run) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const next = await getTeamRun(run.id);
        if (cancelled) return;
        setStatus(next);
        const terminal = TERMINAL.has(next.team?.status ?? 'RUNNING');
        if (terminal) {
          if (!reviewed.current) {
            reviewed.current = true;
            try {
              const report = await reviewTeam(run.id);
              if (cancelled) return;
              if (report?.status === 'repairing') {
                // `finalize` queued bounded repairs; keep watching until they land.
                reviewed.current = false;
                timer = setTimeout(tick, 2500);
                return;
              }
              if (report?.reviewOutcome) setReviewOutcome(report.reviewOutcome);
            } catch {
              /* the synthesis still renders; the review is best-effort */
            }
          }
          try {
            const memo = await getTeamResult(run.id);
            if (!cancelled) setResult(memo);
          } catch {
            /* keep the stage timeline */
          }
          return;
        }
        timer = setTimeout(tick, 2500);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Lost contact with the committee run.');
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [open, run]);

  const stageStatus = useMemo(() => {
    const map: Record<string, string> = {};
    for (const subtask of status?.subtasks ?? []) {
      map[subtask.subtaskId] = subtask.status;
    }
    return map;
  }, [status]);

  const teamStatus = status?.team?.status ?? run?.status;
  const running = Boolean(run) && !TERMINAL.has((teamStatus ?? 'RUNNING') as TeamRunStatus);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users size={16} /> Institution committee
          </DialogTitle>
          <DialogDescription>
            Analyst → debate → trader → risk → PM. Every stage is a real durable task; the
            decision is a proposal, never an order.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <label className="block text-xs font-medium text-muted-foreground">
            Decision question
            <textarea
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              placeholder="e.g. Should we add 2% NVDA to the fund over the next two quarters?"
              rows={3}
              className="mt-1 w-full resize-y rounded-xl border border-border/20 bg-white/5 px-3 py-2 text-sm text-foreground outline-none focus:border-border/40"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-medium text-muted-foreground">
              Universe
              <input
                value={universe}
                onChange={(e) => setUniverse(e.target.value)}
                placeholder="Default: holdings + watchlist"
                className="mt-1 w-full rounded-xl border border-border/20 bg-white/5 px-3 py-2 text-sm text-foreground outline-none focus:border-border/40"
              />
            </label>
            <label className="block text-xs font-medium text-muted-foreground">
              Horizon
              <input
                value={horizon}
                onChange={(e) => setHorizon(e.target.value)}
                placeholder="Default: 3–12 months"
                className="mt-1 w-full rounded-xl border border-border/20 bg-white/5 px-3 py-2 text-sm text-foreground outline-none focus:border-border/40"
              />
            </label>
          </div>

          <label className="block text-xs font-medium text-muted-foreground">
            Constraints (comma separated)
            <input
              value={constraints}
              onChange={(e) => setConstraints(e.target.value)}
              placeholder="e.g. max 5% single name, no leverage, USD only"
              className="mt-1 w-full rounded-xl border border-border/20 bg-white/5 px-3 py-2 text-sm text-foreground outline-none focus:border-border/40"
            />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => void start()} disabled={starting || running || !objective.trim()}>
              {starting ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {starting ? 'Starting…' : 'Run committee'}
            </Button>
            <Button
              variant="outline"
              onClick={() => void seed().then((ok) => { if (ok) onSeeded(); })}
              disabled={seeding}
            >
              {seeding ? <Loader2 size={14} className="animate-spin" /> : <Users size={14} />}
              {existingBots.some((b) => b.action.agentId?.startsWith('institution-'))
                ? 'Refresh committee bots'
                : 'Add committee bots'}
            </Button>
            {run && (
              <Button variant="ghost" onClick={() => { reset(); }}>
                New run
              </Button>
            )}
          </div>
          {(error || seedErrorBase) && (
            <p className="text-xs text-rose-300">{error || seedErrorBase}</p>
          )}
        </div>

        {run && (
          <div className="space-y-3 border-t border-border/10 pt-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="mono">{run.id}</span>
              <span className="rounded-full border border-border/20 px-2 py-0.5">
                {teamStatus ?? 'PLANNING'}
              </span>
              {reviewOutcome && (
                <span className="rounded-full border border-border/20 px-2 py-0.5">
                  review: {reviewOutcome.replaceAll('_', ' ').toLowerCase()}
                </span>
              )}
            </div>

            <ol className="space-y-1.5">
              {STAGE_ORDER.map((stageId) => {
                const state = stageStatus[stageId];
                return (
                  <li
                    key={stageId}
                    className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs ${stageTone(state)}`}
                  >
                    <span className="font-medium">{STAGE_LABELS[stageId]}</span>
                    <span className="mono">{statusLabel(state)}</span>
                  </li>
                );
              })}
            </ol>

            {result && (
              <div className="rounded-xl glass-card-subtle p-3">
                <div className="mb-1 text-xs font-semibold text-muted-foreground">Decision memo</div>
                <pre className="max-h-[24rem] overflow-auto whitespace-pre-wrap break-words text-xs text-foreground">
                  {result}
                </pre>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
