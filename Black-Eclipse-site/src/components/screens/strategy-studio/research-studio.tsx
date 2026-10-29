'use client';

// ── Research studio ─────────────────────────────────────────────────────────
// Robustness without hand-written JSON. The tunable axes are derived from the
// spec, the user edits ranges with min/max/step, and one button runs the whole
// suite (walk-forward → Monte-Carlo → robustness) into a single honest verdict.
// Every number and verdict is the runtime's; a missing measurement is unknown.

import React, { useMemo, useState } from 'react';
import { ResearchResultView } from '@/components/screens/backtest/research-panel';
import {
  backtestClient,
  type ResearchPlan,
  type ResearchRequest,
  type ResearchResult,
  type StrategyRecord,
} from '@/lib/backtest/backtest-client';
import {
  buildParamSpace,
  deriveParamAxes,
  spaceSize,
  type AxisRange,
} from '@/lib/strategy-studio/param-space';
import { summarizeResearch, type SuiteResults } from '@/lib/strategy-studio/research-verdict';
import { Activity, CheckCircle2, HelpCircle, Loader2, ShieldCheck, XCircle } from '@/lib/icons';
import { cn } from '@/lib/utils';

export type ResearchKind = 'optimize' | 'walkForward' | 'monteCarlo' | 'sensitivity' | 'robustness';

type Range = { min: number; max: number; step: number };

const OBJECTIVES = ['sharpe', 'sortino', 'calmar', 'return_drawdown', 'total_return', 'profit_factor'];
const METHODS = ['random', 'grid', 'evolutionary', 'bayesian'];

const INPUT =
  'glass-card-subtle rounded-lg px-2 py-1 font-mono text-[11px] text-foreground outline-none';

function stateIcon(state: 'pass' | 'fail' | 'unknown') {
  if (state === 'pass') return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />;
  if (state === 'fail') return <XCircle className="h-3.5 w-3.5 text-rose-400" />;
  return <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />;
}

export function ResearchStudio({
  selected,
  symbols,
  start,
  end,
  initialCapital,
  running,
  progress,
  onRun,
  onError,
}: {
  selected: StrategyRecord;
  symbols: string[];
  start: string;
  end: string;
  initialCapital: number;
  running: boolean;
  progress?: { stage: string; percent: number } | null;
  onRun: (kind: ResearchKind, body: ResearchRequest) => Promise<ResearchResult | null>;
  onError: (message: string | null) => void;
}) {
  const axes = useMemo(() => deriveParamAxes(selected.spec), [selected.spec]);
  const [enabled, setEnabled] = useState<string[]>(() => axes.map((axis) => axis.path));
  const [ranges, setRanges] = useState<Record<string, Range>>(() =>
    Object.fromEntries(axes.map((axis) => [axis.path, { min: axis.min, max: axis.max, step: axis.step }])),
  );
  const [objective, setObjective] = useState('sharpe');
  const [method, setMethod] = useState('random');
  const [maxEvaluations, setMaxEvaluations] = useState(30);
  const [trainBars, setTrainBars] = useState(250);
  const [testBars, setTestBars] = useState(100);
  const [simulations, setSimulations] = useState(500);
  const [results, setResults] = useState<SuiteResults>({});
  const [busyKind, setBusyKind] = useState<ResearchKind | null>(null);
  const [suiteBusy, setSuiteBusy] = useState(false);
  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);

  const activeRanges: AxisRange[] = axes
    .filter((axis) => enabled.includes(axis.path))
    .map((axis) => ({
      path: axis.path,
      integer: axis.integer,
      min: ranges[axis.path]?.min ?? axis.min,
      max: ranges[axis.path]?.max ?? axis.max,
      step: ranges[axis.path]?.step ?? axis.step,
    }));
  const space = buildParamSpace(activeRanges);
  const combinations = activeRanges.length ? spaceSize(activeRanges) : 0;

  const base = (): ResearchRequest => ({
    strategyId: selected.id,
    symbols: symbols.length ? symbols : undefined,
    start: start || undefined,
    end: end || undefined,
    initialCapital,
    objective,
    save: true,
    background: true,
  });

  const bodyFor = (kind: ResearchKind): ResearchRequest | null => {
    if (kind !== 'monteCarlo' && activeRanges.length === 0) {
      onError('Select at least one parameter to tune before running this research.');
      return null;
    }
    if (kind === 'optimize') return { ...base(), paramSpace: space, method, maxEvaluations };
    if (kind === 'walkForward') {
      return { ...base(), paramSpace: space, method, maxEvaluations, trainBars, testBars };
    }
    if (kind === 'monteCarlo') return { ...base(), method: 'trade_reshuffle', simulations };
    return { ...base(), paramRanges: space };
  };

  const runOne = async (kind: ResearchKind) => {
    onError(null);
    const body = bodyFor(kind);
    if (!body) return null;
    setBusyKind(kind);
    try {
      const result = await onRun(kind, body);
      if (result) setResults((prev) => ({ ...prev, [kind]: result }));
      return result;
    } finally {
      setBusyKind(null);
    }
  };

  const runSuite = async () => {
    if (activeRanges.length === 0) {
      onError('Select at least one parameter to tune before running the suite.');
      return;
    }
    setSuiteBusy(true);
    onError(null);
    setResults({});
    const next: SuiteResults = {};
    try {
      for (const kind of ['walkForward', 'monteCarlo', 'robustness'] as const) {
        const body = bodyFor(kind);
        if (!body) continue;
        const result = await onRun(kind, body);
        if (result) {
          next[kind] = result;
          setResults((prev) => ({ ...prev, [kind]: result }));
        }
      }
    } finally {
      setResults(next);
      setSuiteBusy(false);
    }
  };

  const summary = summarizeResearch(results);
  const busy = suiteBusy || running || Boolean(busyKind);

  const loadPlan = async () => {
    setPlanBusy(true);
    setPlanError(null);
    onError(null);
    try {
      setPlan(
        await backtestClient.researchPlan(selected.id, {
          start: start || undefined,
          end: end || undefined,
          objective,
          trainBars,
          testBars,
          maxEvaluations,
        }),
      );
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : 'the research plan could not be loaded');
    } finally {
      setPlanBusy(false);
    }
  };

  const toggle = (path: string) =>
    setEnabled((prev) => (prev.includes(path) ? prev.filter((item) => item !== path) : [...prev, path]));

  const setRange = (path: string, patch: Partial<Range>) =>
    setRanges((prev) => ({ ...prev, [path]: { ...(prev[path] ?? { min: 1, max: 1, step: 1 }), ...patch } }));

  return (
    <div className="glass-card flex flex-col gap-3 rounded-2xl p-4">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold text-foreground">Robustness</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          walk-forward · Monte-Carlo · sensitivity · overtrading
        </span>
        <button
          type="button"
          onClick={() => void runSuite()}
          disabled={busy}
          className="glass-button-add ml-auto flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
        >
          {suiteBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
          {suiteBusy ? 'Running suite…' : 'Run the robustness suite'}
        </button>
      </div>

      {axes.length === 0 ? (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          This spec has no numeric parameters to tune. Monte-Carlo can still run; add an indicator period or a
          stop/target value to enable optimization and walk-forward.
        </p>
      ) : (
        <div className="rounded-xl border border-white/10 p-2">
          <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
            <Activity className="h-3 w-3" /> Parameters to search
            <span className="ml-auto normal-case tracking-normal">
              {activeRanges.length} selected · {combinations} combination{combinations === 1 ? '' : 's'}
            </span>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-left font-mono text-[10px]">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="px-1 py-0.5">On</th>
                  <th className="px-1 py-0.5">Parameter</th>
                  <th className="px-1 py-0.5 text-right">Base</th>
                  <th className="px-1 py-0.5 text-right">Min</th>
                  <th className="px-1 py-0.5 text-right">Max</th>
                  <th className="px-1 py-0.5 text-right">Step</th>
                </tr>
              </thead>
              <tbody>
                {axes.map((axis) => {
                  const range = ranges[axis.path] ?? { min: axis.min, max: axis.max, step: axis.step };
                  const on = enabled.includes(axis.path);
                  return (
                    <tr key={axis.path} className={cn('border-t border-white/5', !on && 'opacity-50')}>
                      <td className="px-1 py-0.5">
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={() => toggle(axis.path)}
                          aria-label={`Tune ${axis.label}`}
                        />
                      </td>
                      <td className="px-1 py-0.5 text-foreground">{axis.label}</td>
                      <td className="px-1 py-0.5 text-right text-muted-foreground">{axis.base}</td>
                      <td className="px-1 py-0.5 text-right">
                        <input
                          type="number"
                          value={range.min}
                          disabled={!on}
                          onChange={(event) => setRange(axis.path, { min: Number(event.target.value) })}
                          className={cn(INPUT, 'w-16 text-right')}
                          aria-label={`${axis.label} minimum`}
                        />
                      </td>
                      <td className="px-1 py-0.5 text-right">
                        <input
                          type="number"
                          value={range.max}
                          disabled={!on}
                          onChange={(event) => setRange(axis.path, { max: Number(event.target.value) })}
                          className={cn(INPUT, 'w-16 text-right')}
                          aria-label={`${axis.label} maximum`}
                        />
                      </td>
                      <td className="px-1 py-0.5 text-right">
                        <input
                          type="number"
                          value={range.step}
                          min={axis.integer ? 1 : 0.01}
                          disabled={!on}
                          onChange={(event) => setRange(axis.path, { step: Number(event.target.value) })}
                          className={cn(INPUT, 'w-16 text-right')}
                          aria-label={`${axis.label} step`}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {combinations > maxEvaluations ? (
            <p className="mt-1 text-[9px] leading-relaxed text-amber-200/80">
              The grid is larger than the evaluation budget: a random search will test {maxEvaluations} of{' '}
              {combinations} combinations.
            </p>
          ) : null}
        </div>
      )}

      <details className="rounded-xl border border-white/10 p-2">
        <summary className="cursor-pointer text-[11px] text-muted-foreground">
          Research plan
          <span className="ml-2 text-[9px]">hypothesis · acceptance criteria · biases</span>
        </summary>
        <div className="mt-2 flex flex-col gap-2 text-[11px]">
          {planBusy ? (
            <span className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> building the plan…
            </span>
          ) : null}
          {planError ? <p className="font-mono text-[10px] text-rose-300">{planError}</p> : null}
          {!plan && !planBusy ? (
            <button
              type="button"
              onClick={() => void loadPlan()}
              className="glass-button self-start rounded-lg px-2.5 py-1 text-[11px]"
            >
              Load the research plan
            </button>
          ) : null}
          {plan ? (
            <>
              {plan.hypothesis ? (
                <p className="leading-relaxed text-foreground">{plan.hypothesis}</p>
              ) : null}
              {plan.assumptions?.length ? (
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Assumptions</p>
                  <ul className="mt-0.5 space-y-0.5">
                    {plan.assumptions.map((item, index) => (
                      <li key={index} className="text-muted-foreground">• {item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {plan.acceptanceCriteria?.length ? (
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Acceptance criteria</p>
                  <ul className="mt-0.5 space-y-0.5">
                    {plan.acceptanceCriteria.map((item, index) => (
                      <li key={index} className="text-muted-foreground">• {item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {plan.potentialBiases?.length ? (
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Potential biases</p>
                  <ul className="mt-0.5 space-y-0.5">
                    {plan.potentialBiases.map((item, index) => (
                      <li key={index} className="text-amber-200/80">• {item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <button
                type="button"
                onClick={() => void loadPlan()}
                className="glass-button self-start rounded-lg px-2 py-0.5 text-[10px]"
              >
                Refresh plan
              </button>
            </>
          ) : null}
        </div>
      </details>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Objective
          <select value={objective} onChange={(event) => setObjective(event.target.value)} className={INPUT}>
            {OBJECTIVES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Method
          <select value={method} onChange={(event) => setMethod(event.target.value)} className={INPUT}>
            {METHODS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Max evaluations
          <input
            type="number"
            min={1}
            value={maxEvaluations}
            onChange={(event) => setMaxEvaluations(Number(event.target.value) || 1)}
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Simulations
          <input
            type="number"
            min={1}
            value={simulations}
            onChange={(event) => setSimulations(Number(event.target.value) || 1)}
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Train bars
          <input
            type="number"
            min={10}
            value={trainBars}
            onChange={(event) => setTrainBars(Number(event.target.value) || 10)}
            className={INPUT}
          />
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Test bars
          <input
            type="number"
            min={5}
            value={testBars}
            onChange={(event) => setTestBars(Number(event.target.value) || 5)}
            className={INPUT}
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            ['optimize', 'Optimize'],
            ['walkForward', 'Walk-forward'],
            ['monteCarlo', 'Monte Carlo'],
            ['sensitivity', 'Sensitivity'],
            ['robustness', 'Robustness'],
          ] as const
        ).map(([kind, label]) => (
          <button
            key={kind}
            type="button"
            disabled={busy}
            onClick={() => void runOne(kind)}
            className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
          >
            {busyKind === kind ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {label}
          </button>
        ))}
        {running && progress ? (
          <span className="font-mono text-[10px] text-muted-foreground">
            {progress.stage} {Math.round(progress.percent)}%
          </span>
        ) : null}
      </div>

      {summary.checks.length > 0 ? (
        <div className="rounded-xl border border-white/10 p-3">
          <div className="mb-2 flex items-center gap-2">
            <span
              className={cn(
                'rounded-md border px-2 py-0.5 font-mono text-[10px] uppercase',
                summary.overall === 'robust'
                  ? 'border-emerald-500/40 text-emerald-400'
                  : summary.overall === 'fragile'
                    ? 'border-rose-500/40 text-rose-400'
                    : 'border-amber-500/40 text-amber-400',
              )}
            >
              {summary.overall}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {summary.overall === 'robust'
                ? 'every scored check passed'
                : summary.overall === 'fragile'
                  ? 'at least one scored check failed'
                  : 'not enough measurements to call it robust'}
            </span>
          </div>
          <ul className="space-y-1">
            {summary.checks.map((check) => (
              <li key={check.id} className="flex items-start gap-2 text-[11px]">
                <span className="mt-0.5">{stateIcon(check.state)}</span>
                <span className="min-w-0 flex-1">
                  <span className={cn('text-foreground', check.kind === 'info' && 'text-muted-foreground')}>
                    {check.label}
                  </span>
                  <span className="ml-2 font-mono text-[10px] text-muted-foreground">{check.detail}</span>
                </span>
                {check.kind === 'info' ? (
                  <span className="font-mono text-[9px] text-muted-foreground/60">info</span>
                ) : null}
              </li>
            ))}
          </ul>
          {summary.notes.length ? (
            <ul className="mt-2 space-y-0.5">
              {summary.notes.map((note, index) => (
                <li key={index} className="text-[10px] leading-relaxed text-muted-foreground">
                  • {note}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {Object.entries(results).map(([kind, result]) =>
        result ? (
          <details key={kind} className="rounded-xl border border-white/10 p-2">
            <summary className="cursor-pointer text-[11px] text-foreground">
              {kind} result
              <span className="ml-2 font-mono text-[10px] text-muted-foreground">
                {result.experimentId ?? result.status}
              </span>
            </summary>
            <div className="mt-2">
              <ResearchResultView research={result} />
            </div>
          </details>
        ) : null,
      )}
    </div>
  );
}
