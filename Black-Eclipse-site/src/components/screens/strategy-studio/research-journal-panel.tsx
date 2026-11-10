'use client';

// ── Research journal (Strategy Studio) ──────────────────────────────────────
// A persistent, pre-registered research program: the question, the hypotheses
// registered BEFORE testing, the trials, and the ideas that were rejected. This
// is the anti-p-hacking surface: the trial ledger is what the multiple-testing
// diagnostics should count.

import React, { useCallback, useEffect, useState } from 'react';
import {
  backtestClient,
  type ResearchJournal,
  type ResearchSession,
} from '@/lib/backtest/backtest-client';
import { BookOpen, Loader2, RefreshCw } from '@/lib/icons';

export interface ResearchJournalPanelProps {
  strategyId?: string | null;
  experimentId?: string | null;
  onError?: (message: string | null) => void;
}

export function ResearchJournalPanel({ strategyId, experimentId, onError }: ResearchJournalPanelProps) {
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [journal, setJournal] = useState<ResearchJournal | null>(null);
  const [title, setTitle] = useState('Research program');
  const [statement, setStatement] = useState('');
  const [acceptance, setAcceptance] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await backtestClient.listSessions(50);
      setSessions(list);
      if (!sessionId && list.length) setSessionId(list[0].id);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'journal unavailable');
    }
  }, [onError, sessionId]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!sessionId) { setJournal(null); return; }
    let active = true;
    void backtestClient.getJournal(sessionId)
      .then((j) => active && setJournal(j))
      .catch((e: unknown) => active && onError?.(e instanceof Error ? e.message : 'journal unavailable'));
    return () => { active = false; };
  }, [sessionId, onError]);

  const create = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    onError?.(null);
    try {
      const session = await backtestClient.createSession({
        title: title.trim() || 'Research program',
        strategyId: strategyId ?? undefined,
      });
      setSessions((prev) => [session, ...prev]);
      setSessionId(session.id);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'could not create session');
    } finally {
      setBusy(false);
    }
  }, [busy, title, strategyId, onError]);

  const register = useCallback(async () => {
    if (!sessionId || !statement.trim() || busy) return;
    setBusy(true);
    onError?.(null);
    try {
      await backtestClient.registerHypothesis(sessionId, {
        statement: statement.trim(),
        acceptance: acceptance.trim() || undefined,
        metric: 'sharpe',
      });
      setStatement('');
      setAcceptance('');
      setJournal(await backtestClient.getJournal(sessionId));
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'could not register hypothesis');
    } finally {
      setBusy(false);
    }
  }, [sessionId, statement, acceptance, busy, onError]);

  const record = useCallback(async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    onError?.(null);
    try {
      await backtestClient.recordTrial(sessionId, {
        kind: 'backtest',
        experimentId: experimentId ?? undefined,
      });
      setJournal(await backtestClient.getJournal(sessionId));
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'could not record trial');
    } finally {
      setBusy(false);
    }
  }, [sessionId, experimentId, busy, onError]);

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <BookOpen className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Research journal</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          pre-register · trials · rejected ideas
        </span>
        <button
          type="button"
          onClick={() => void load()}
          className="glass-card-subtle ml-auto inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px]"
        >
          <RefreshCw className="h-3 w-3" /> Refresh
        </button>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="space-y-2">
          <label className="block text-[11px] text-muted-foreground">
            Session
            <select
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              className="glass-card-subtle mt-1 w-full rounded-lg px-2 py-1.5 text-xs"
            >
              <option value="">New session…</option>
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>{s.title}</option>
              ))}
            </select>
          </label>
          <div className="flex gap-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Session title"
              className="glass-card-subtle min-w-0 flex-1 rounded-lg px-2 py-1.5 text-xs"
            />
            <button
              type="button"
              onClick={() => void create()}
              disabled={busy}
              className="glass-card-subtle rounded-lg px-2.5 py-1.5 text-[11px] disabled:opacity-50"
            >
              Create
            </button>
          </div>
          <textarea
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            placeholder="Hypothesis registered BEFORE testing (e.g. 20/50 EMA crossover has positive OOS Sharpe on EURUSD)"
            rows={2}
            className="glass-card-subtle w-full rounded-lg px-2 py-1.5 text-xs"
          />
          <div className="flex gap-2">
            <input
              value={acceptance}
              onChange={(e) => setAcceptance(e.target.value)}
              placeholder="Acceptance criterion (optional)"
              className="glass-card-subtle min-w-0 flex-1 rounded-lg px-2 py-1.5 text-xs"
            />
            <button
              type="button"
              onClick={() => void register()}
              disabled={busy || !sessionId || !statement.trim()}
              className="glass-card-subtle rounded-lg px-2.5 py-1.5 text-[11px] disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Register'}
            </button>
          </div>
          <button
            type="button"
            onClick={() => void record()}
            disabled={busy || !sessionId || !experimentId}
            className="glass-card-subtle w-full rounded-lg px-2.5 py-1.5 text-[11px] disabled:opacity-50"
          >
            Record current experiment as a trial
          </button>
        </div>

        <div className="rounded-xl border border-white/5 bg-black/10 p-3">
          {!sessionId ? (
            <p className="text-xs text-muted-foreground">
              No session selected. Create one to make this research auditable.
            </p>
          ) : journal ? (
            <div className="space-y-2 text-[11px]">
              <div className="grid grid-cols-3 gap-2 text-center">
                <Stat label="Hypotheses" value={journal.hypothesisCount} />
                <Stat label="Trials" value={journal.trialCount} />
                <Stat label="Tested" value={journal.testedHypotheses} />
              </div>
              {journal.openQuestions.length ? (
                <div>
                  <p className="text-muted-foreground">Open questions</p>
                  <ul className="mt-1 space-y-1">
                    {journal.openQuestions.slice(0, 4).map((q) => (
                      <li key={q} className="line-clamp-2">• {q}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-muted-foreground">No open hypotheses.</p>
              )}
              {journal.rejectedHypotheses.length ? (
                <p className="text-amber-300">
                  {journal.rejectedHypotheses.length} rejected idea(s) kept on record.
                </p>
              ) : null}
              {journal.recentTrials.length ? (
                <div>
                  <p className="text-muted-foreground">Recent trials</p>
                  <ul className="mt-1 space-y-0.5 font-mono">
                    {journal.recentTrials.slice(-4).reverse().map((t) => (
                      <li key={String(t.id)} className="truncate">
                        {String(t.kind)} · {String(t.experimentId ?? 'no experiment')}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Loading journal…</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-white/5 bg-black/20 px-2 py-1.5">
      <p className="text-base font-semibold">{value}</p>
      <p className="text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}
