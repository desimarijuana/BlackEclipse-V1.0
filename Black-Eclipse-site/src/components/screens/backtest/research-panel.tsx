'use client';

// ── Research panel — optimization / walk-forward / Monte-Carlo / robustness ──
// Runs the deterministic research engines through the same front door as the
// backtest and renders their structured results. Nothing is simulated: every
// number is the runtime's output, and a non-robust verdict is shown as-is.

import React, { useMemo, useState } from 'react';
import { formatMetric, type ResearchRequest, type ResearchResult, type StrategyRecord } from '@/lib/backtest/backtest-client';
import { cn } from '@/lib/utils';
import { Activity, AlertTriangle, Loader2 } from '@/lib/icons';

export interface ResearchPanelProps {
  selected: StrategyRecord | null;
  running: boolean;
  research: ResearchResult | null;
  progress?: { stage: string; percent: number } | null;
  onRun: (kind: 'optimize' | 'walkForward' | 'monteCarlo' | 'sensitivity' | 'robustness',
           body: ResearchRequest) => Promise<ResearchResult | null>;
  onError: (message: string | null) => void;
}

const OBJECTIVES = ['sharpe', 'sortino', 'calmar', 'return_drawdown', 'total_return', 'profit_factor'];
const METHODS = ['random', 'grid', 'evolutionary', 'bayesian'];

function defaultSpace(spec: Record<string, unknown> | undefined): string {
  const indicators = (spec?.indicators as Array<Record<string, unknown>> | undefined) ?? [];
  const space: Record<string, number[]> = {};
  indicators.slice(0, 2).forEach((decl, i) => {
    const period = (decl.params as { period?: number } | undefined)?.period;
    if (typeof period === 'number') {
      const base = Math.max(2, Math.round(period));
      space[`indicators.${i}.params.period`] = Array.from(new Set([
        Math.max(2, base - 2), base, base + 2, base + 5,
      ].filter((v) => v >= 2))).sort((a, b) => a - b);
    }
  });
  return JSON.stringify(space, null, 2);
}

function Badge({ verdict }: { verdict?: string }) {
  const tone = verdict === 'robust' ? 'text-emerald-400 border-emerald-500/30'
    : verdict === 'fragile' ? 'text-rose-400 border-rose-500/30'
    : 'text-amber-400 border-amber-500/30';
  return <span className={cn('rounded-md border px-2 py-0.5 font-mono text-[10px] uppercase', tone)}>{verdict}</span>;
}

export function ResearchPanel({ selected, running, research, progress, onRun, onError }: ResearchPanelProps) {
  const [objective, setObjective] = useState('sharpe');
  const [method, setMethod] = useState('random');
  const [spaceText, setSpaceText] = useState(() => defaultSpace(selected?.spec));
  const [maxEvaluations, setMaxEvaluations] = useState(20);
  const [trainBars, setTrainBars] = useState(250);
  const [testBars, setTestBars] = useState(100);
  const [simulations, setSimulations] = useState(500);
  const [background, setBackground] = useState(true);

  const resetSpace = () => setSpaceText(defaultSpace(selected?.spec));

  const parseSpace = (): Record<string, unknown> | null => {
    try {
      return JSON.parse(spaceText) as Record<string, unknown>;
    } catch (err) {
      onError(err instanceof Error ? err.message : 'invalid parameter-space JSON');
      return null;
    }
  };

  const base = (): ResearchRequest | null => {
    if (!selected) {
      onError('Select a strategy first.');
      return null;
    }
    return { strategyId: selected.id, objective, save: true };
  };

  const trigger = (kind: Parameters<ResearchPanelProps['onRun']>[0]) => {
    onError(null);
    const b = base();
    if (!b) return;
    b.background = background;
    if (kind === 'optimize' || kind === 'walkForward') {
      const space = parseSpace();
      if (!space) return;
      b.paramSpace = space;
      b.method = method;
      b.maxEvaluations = maxEvaluations;
    }
    if (kind === 'walkForward') { b.trainBars = trainBars; b.testBars = testBars; }
    if (kind === 'monteCarlo') { b.method = 'trade_reshuffle'; b.simulations = simulations; }
    if (kind === 'sensitivity' || kind === 'robustness') {
      const space = parseSpace();
      if (!space) return;
      b.paramRanges = space;
    }
    void onRun(kind, b);
  };

  const buttons = useMemo(() => ([
    ['optimize', 'Optimize'], ['walkForward', 'Walk-Forward'], ['monteCarlo', 'Monte Carlo'],
    ['sensitivity', 'Sensitivity'], ['robustness', 'Robustness'],
  ] as const), []);

  return (
    <div className="glass-card flex flex-col gap-3 rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <Activity className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold text-foreground">Research</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          optimization · walk-forward · Monte-Carlo · robustness
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Objective
          <select value={objective} onChange={(e) => setObjective(e.target.value)}
            className="glass-card-subtle rounded-lg px-2 py-1 text-[11px] text-foreground outline-none">
            {OBJECTIVES.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Method
          <select value={method} onChange={(e) => setMethod(e.target.value)}
            className="glass-card-subtle rounded-lg px-2 py-1 text-[11px] text-foreground outline-none">
            {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Max evals
          <input type="number" value={maxEvaluations} min={1}
            onChange={(e) => setMaxEvaluations(Number(e.target.value) || 1)}
            className="glass-card-subtle rounded-lg px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Simulations
          <input type="number" value={simulations} min={1}
            onChange={(e) => setSimulations(Number(e.target.value) || 1)}
            className="glass-card-subtle rounded-lg px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Train bars
          <input type="number" value={trainBars} min={10}
            onChange={(e) => setTrainBars(Number(e.target.value) || 10)}
            className="glass-card-subtle rounded-lg px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Test bars
          <input type="number" value={testBars} min={5}
            onChange={(e) => setTestBars(Number(e.target.value) || 5)}
            className="glass-card-subtle rounded-lg px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
        </label>
      </div>

      <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-2">
          Parameter space (JSON: path → values / range)
          <button type="button" onClick={resetSpace} className="glass-button rounded-md px-2 py-0.5 text-[10px]">
            Reset from strategy
          </button>
        </span>
        <textarea value={spaceText} onChange={(e) => setSpaceText(e.target.value)} spellCheck={false}
          className="h-[110px] w-full resize-y rounded-lg border border-white/10 bg-black/30 p-2 font-mono text-[10px] text-foreground outline-none" />
      </label>

      <div className="flex flex-wrap items-center gap-3">
        {buttons.map(([kind, label]) => (
          <button key={kind} type="button" disabled={running} onClick={() => trigger(kind)}
            className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50">
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {label}
          </button>
        ))}
        <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <input type="checkbox" checked={background} onChange={(e) => setBackground(e.target.checked)} />
          Run in background
        </label>
        {running && progress && (
          <span className="font-mono text-[10px] text-muted-foreground">
            {progress.stage} {Math.round(progress.percent)}%
          </span>
        )}
      </div>

      {research && <ResearchResultView research={research} />}
    </div>
  );
}

export function ResearchResultView({ research }: { research: ResearchResult }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-white/10 p-3">
      <div className="flex items-center gap-2 font-mono text-[11px]">
        <span className="text-foreground">{research.kind}</span>
        {research.verdict && <Badge verdict={research.verdict} />}
        {research.experimentId && <span className="text-muted-foreground">{research.experimentId}</span>}
        <span className="ml-auto text-muted-foreground">{research.status}</span>
      </div>

      {research.warnings?.length > 0 && (
        <ul className="space-y-0.5">
          {research.warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-1 font-mono text-[10px] text-amber-300">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              <span><b>{w.code}</b>: {w.message}</span>
            </li>
          ))}
        </ul>
      )}

      {research.kind === 'optimization' && research.best && (
        <div>
          <div className="font-mono text-[10px] text-muted-foreground">
            best score {formatMetric('sharpe', research.best.score)} · trades {research.best.metrics.trade_count ?? '—'}
          </div>
          <pre className="mt-1 max-h-[120px] overflow-auto rounded bg-black/30 p-2 font-mono text-[10px] text-muted-foreground">
            {JSON.stringify(research.best.params, null, 2)}
          </pre>
          {research.leaderboard && (
            <table className="mt-2 w-full text-left font-mono text-[10px]">
              <thead className="text-muted-foreground"><tr><th className="px-1">#</th><th className="px-1">Score</th><th className="px-1">Params</th></tr></thead>
              <tbody>
                {research.leaderboard.slice(0, 8).map((t, i) => (
                  <tr key={i} className="border-t border-white/5">
                    <td className="px-1">{i + 1}</td>
                    <td className="px-1">{t.score == null ? '—' : t.score.toFixed(3)}</td>
                    <td className="truncate px-1 text-muted-foreground">{JSON.stringify(t.params)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {research.kind === 'walk_forward' && research.windows && (
        <div className="max-h-[220px] overflow-auto">
          <table className="w-full text-left font-mono text-[10px]">
            <thead className="text-muted-foreground sticky top-0 bg-black/30">
              <tr><th className="px-1">Test window</th><th className="px-1 text-right">IS Sharpe</th>
                  <th className="px-1 text-right">OOS Sharpe</th><th className="px-1 text-right">OOS Ret%</th>
                  <th className="px-1 text-right">OOS Trades</th></tr>
            </thead>
            <tbody>
              {research.windows.map((w, i) => (
                <tr key={i} className="border-t border-white/5">
                  <td className="px-1">{w.test.start} → {w.test.end}</td>
                  <td className="px-1 text-right">{w.inSample.sharpe?.toFixed(2) ?? '—'}</td>
                  <td className="px-1 text-right">{w.outOfSample.sharpe?.toFixed(2) ?? '—'}</td>
                  <td className="px-1 text-right">{w.outOfSample.total_return?.toFixed(2) ?? '—'}</td>
                  <td className="px-1 text-right">{w.outOfSample.trade_count ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-1 font-mono text-[10px] text-muted-foreground">
            combined OOS return {formatMetric('total_return', research.metrics.total_return)} ·
            divergence {research.divergence?.outOfSample?.toFixed(3) ?? '—'} vs {research.divergence?.inSample?.toFixed(3) ?? '—'}
          </div>
        </div>
      )}

      {research.kind === 'monte_carlo' && research.returnPercentiles && (
        <div className="grid grid-cols-3 gap-2 font-mono text-[10px] sm:grid-cols-4">
          {(['p5', 'p25', 'p50', 'p75', 'p95'] as const).map((p) => (
            <div key={p} className="glass-card-subtle rounded-lg px-2 py-1">
              <div className="text-muted-foreground">{p}</div>
              <div>{research.returnPercentiles![p]?.toFixed(2)}%</div>
            </div>
          ))}
          <div className="glass-card-subtle rounded-lg px-2 py-1">
            <div className="text-muted-foreground">P(loss)</div>
            <div>{research.probabilityOfLoss?.toFixed(1)}%</div>
          </div>
          <div className="glass-card-subtle rounded-lg px-2 py-1">
            <div className="text-muted-foreground">P(ruin)</div>
            <div>{research.probabilityOfRuin?.toFixed(1)}%</div>
          </div>
          <div className="glass-card-subtle rounded-lg px-2 py-1">
            <div className="text-muted-foreground">worst DD</div>
            <div>{research.worstDrawdown?.toFixed(2)}%</div>
          </div>
        </div>
      )}

      {research.kind === 'sensitivity' && research.parameters && (
        <table className="w-full text-left font-mono text-[10px]">
          <thead className="text-muted-foreground"><tr><th className="px-1">Parameter</th>
            <th className="px-1 text-right">Best</th><th className="px-1 text-center">Collapse</th>
            <th className="px-1 text-center">Stable</th></tr></thead>
          <tbody>
            {Object.entries(research.parameters).map(([path, p]) => (
              <tr key={path} className="border-t border-white/5">
                <td className="px-1">{path}</td>
                <td className="px-1 text-right">{p.best == null ? '—' : p.best.toFixed(3)}</td>
                <td className="px-1 text-center">{p.collapse ? 'yes' : 'no'}</td>
                <td className="px-1 text-center">{p.stable ? 'yes' : 'no'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {research.kind === 'robustness' && (
        <div className="flex flex-col gap-2">
          {research.conclusions?.length ? (
            <ul className="space-y-0.5">{research.conclusions.map((c, i) => (
              <li key={i} className="font-mono text-[10px] text-foreground">• {c}</li>))}</ul>
          ) : <p className="font-mono text-[10px] text-muted-foreground">No robustness concerns detected.</p>}
          {research.costSensitivity && (
            <table className="w-full text-left font-mono text-[10px]">
              <thead className="text-muted-foreground"><tr><th className="px-1">Cost ×</th>
                <th className="px-1 text-right">Objective</th><th className="px-1 text-right">Return%</th></tr></thead>
              <tbody>{research.costSensitivity.map((r) => (
                <tr key={r.multiplier} className="border-t border-white/5">
                  <td className="px-1">{r.multiplier}×</td>
                  <td className="px-1 text-right">{r.objective == null ? '—' : r.objective.toFixed(3)}</td>
                  <td className="px-1 text-right">{r.totalReturn?.toFixed(2) ?? '—'}</td>
                </tr>))}</tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
