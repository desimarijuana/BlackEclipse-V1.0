'use client';

// Factor & Alpha Research Lab — a workbench over the real Python engine.
// No mocked metrics: every value shown comes from a persisted evaluation,
// portfolio run or registry record returned by /api/factors.

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import {
  factorsClient,
  type EvaluationResult,
  type FactorRecord,
  type LibraryFactor,
  type PortfolioResult,
} from '@/lib/factors-client';

type Tab = 'overview' | 'library' | 'builder' | 'evaluation' | 'portfolio';

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'library', label: 'Factor Library' },
  { id: 'builder', label: 'Factor Builder' },
  { id: 'evaluation', label: 'Alpha Evaluation' },
  { id: 'portfolio', label: 'Quantile Portfolio' },
];

function Sparkline({ values, className }: { values: (number | null)[]; className?: string }) {
  const finite = values.map((v, i) => ({ v, i })).filter((p) => p.v !== null && Number.isFinite(p.v));
  if (finite.length < 2) return <div className={cn('text-xs text-white/40', className)}>not enough points</div>;
  const xs = finite.map((p) => p.i);
  const ys = finite.map((p) => p.v as number);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const pts = finite
    .map((p) => `${(((p.i - minX) / spanX) * 100).toFixed(2)},${(100 - (((p.v as number) - minY) / spanY) * 100).toFixed(2)}`)
    .join(' ');
  const zeroY = 100 - ((0 - minY) / spanY) * 100;
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className={cn('h-24 w-full', className)}>
      {minY < 0 && maxY > 0 && <line x1="0" y1={zeroY} x2="100" y2={zeroY} stroke="currentColor" strokeOpacity="0.2" strokeWidth="0.5" />}
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="glass-card-subtle rounded-lg p-3" title={hint}>
      <div className="text-[10px] uppercase tracking-wide text-white/50">{label}</div>
      <div className="text-lg font-medium text-white">{value}</div>
    </div>
  );
}

const fmt = (v: number | null | undefined, digits = 4) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toFixed(digits);

export function FactorLabScreen() {
  const [tab, setTab] = useState<Tab>('overview');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [factors, setFactors] = useState<FactorRecord[]>([]);
  const [library, setLibrary] = useState<LibraryFactor[]>([]);

  const [name, setName] = useState('My Momentum');
  const [family, setFamily] = useState('momentum');
  const [expression, setExpression] = useState('pct_change(close, 21)');
  const [symbols, setSymbols] = useState('AAPL, MSFT, NVDA, AMZN, GOOGL, META, JPM, XOM');
  const [horizons, setHorizons] = useState('1,5,21');
  const [quantiles, setQuantiles] = useState(5);
  const [costBps, setCostBps] = useState(10);
  const [rebalance, setRebalance] = useState(21);

  const [validation, setValidation] = useState<{ valid: boolean; variables: string[]; errors: { message: string }[] } | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioResult | null>(null);

  const symbolList = useCallback(
    () => symbols.split(',').map((s) => s.trim()).filter(Boolean),
    [symbols],
  );

  const refresh = useCallback(async () => {
    try {
      const [f, lib] = await Promise.all([factorsClient.listFactors(), factorsClient.library()]);
      setFactors(f.factors);
      setLibrary(lib.library);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load factors');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'request failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full w-full flex-col gap-4 overflow-y-auto p-4 text-white/90">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Factor &amp; Alpha Research Lab</h1>
          <p className="text-xs text-white/50">
            Deterministic factor research — real formulas, real IC, real portfolio accounting.
          </p>
        </div>
        <div className="glass-card-subtle flex gap-1 rounded-lg p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'rounded-md px-3 py-1.5 text-xs transition',
                tab === t.id ? 'bg-white/15 text-white' : 'text-white/60 hover:text-white',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div className="glass-card-subtle rounded-lg border border-red-500/30 p-3 text-xs text-red-300">
          {error}{' '}
          <button className="underline" onClick={() => void refresh()}>
            retry
          </button>
        </div>
      )}

      {tab === 'overview' && (
        <section className="grid gap-4 md:grid-cols-2">
          <div className="glass-card rounded-xl p-4">
            <h2 className="mb-2 text-sm font-medium">Saved factors ({factors.length})</h2>
            {factors.length === 0 ? (
              <p className="text-xs text-white/50">
                No factors yet. Open the Factor Builder to create one, or install the built-in library.
              </p>
            ) : (
              <ul className="space-y-1 text-xs">
                {factors.slice(0, 8).map((f) => (
                  <li key={f.id} className="flex items-center justify-between gap-2 border-b border-white/5 py-1">
                    <span className="truncate">{f.name}</span>
                    <span className="text-white/40">
                      v{f.latestVersion} · {f.family} · {f.validationStatus}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="glass-card rounded-xl p-4">
            <h2 className="mb-2 text-sm font-medium">Data readiness</h2>
            <p className="text-xs text-white/50">
              Evaluation fetches verified market data through the shared gateway and computes IC /
              Rank IC / decay with an explicit missing-data policy. Factors whose inputs are not
              supplied by the data surface are marked unavailable in the library — never fabricated.
            </p>
          </div>
        </section>
      )}

      {tab === 'library' && (
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {library.map((f) => (
            <div key={f.name} className="glass-card rounded-xl p-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">{f.name}</h3>
                <span className={cn('rounded-full px-2 py-0.5 text-[10px]', f.available ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white/10 text-white/40')}>
                  {f.available ? 'available' : 'unavailable'}
                </span>
              </div>
              <p className="mt-1 text-xs text-white/60">{f.description}</p>
              <code className="mt-2 block truncate rounded bg-black/30 px-2 py-1 text-[11px] text-white/80">
                {f.expression || '—'}
              </code>
              <div className="mt-2 text-[10px] text-white/40">
                {f.family} · lookback {f.lookback} · {f.inputs.join(', ')}
              </div>
              {!f.available && f.unavailableReason && (
                <p className="mt-1 text-[10px] text-amber-300/80">{f.unavailableReason}</p>
              )}
              {f.available && (
                <button
                  className="mt-2 text-[11px] text-sky-300 underline"
                  onClick={() => {
                    setExpression(f.expression);
                    setName(f.name);
                    setFamily(f.family);
                    setTab('builder');
                  }}
                >
                  use in builder
                </button>
              )}
            </div>
          ))}
        </section>
      )}

      {tab === 'builder' && (
        <section className="grid gap-4 lg:grid-cols-2">
          <div className="glass-card rounded-xl p-4">
            <h2 className="mb-3 text-sm font-medium">Factor definition</h2>
            <label className="mb-2 block text-xs text-white/60">
              Name
              <input className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 text-sm" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="mb-2 block text-xs text-white/60">
              Family
              <input className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 text-sm" value={family} onChange={(e) => setFamily(e.target.value)} />
            </label>
            <label className="mb-2 block text-xs text-white/60">
              Formula
              <textarea
                rows={3}
                className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 font-mono text-xs"
                value={expression}
                onChange={(e) => setExpression(e.target.value)}
              />
            </label>
            <div className="flex gap-2">
              <button
                disabled={busy}
                className="rounded-md bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20 disabled:opacity-50"
                onClick={() => void run(async () => setValidation(await factorsClient.validate({ expression })))}
              >
                Validate
              </button>
              <button
                disabled={busy}
                className="rounded-md bg-sky-500/20 px-3 py-1.5 text-xs text-sky-200 hover:bg-sky-500/30 disabled:opacity-50"
                onClick={() =>
                  void run(async () => {
                    await factorsClient.createFactor({ name, family, expression, direction: 'positive' });
                    await refresh();
                  })
                }
              >
                Save version
              </button>
            </div>
            {validation && (
              <div className={cn('mt-3 rounded-md p-2 text-xs', validation.valid ? 'bg-emerald-500/10 text-emerald-200' : 'bg-red-500/10 text-red-300')}>
                {validation.valid ? `valid · inputs: ${validation.variables.join(', ') || '—'}` : validation.errors.map((e) => e.message).join('; ')}
              </div>
            )}
          </div>
          <div className="glass-card rounded-xl p-4">
            <h2 className="mb-3 text-sm font-medium">Supported operations</h2>
            <p className="text-xs text-white/60">
              The formula language is the shared safe AST evaluator: arithmetic, comparisons,
              time-series ops (lag, diff, pct_change, rolling_mean/std/min/max/quantile, sma, ema,
              rsi, macd, atr) and cross-sectional ops (rank, zscore, winsorize, demean, neutralize).
              No arbitrary code is ever executed.
            </p>
          </div>
        </section>
      )}

      {tab === 'evaluation' && (
        <section className="space-y-4">
          <div className="glass-card rounded-xl p-4">
            <div className="grid gap-3 md:grid-cols-3">
              <label className="text-xs text-white/60">
                Formula
                <input className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 font-mono text-xs" value={expression} onChange={(e) => setExpression(e.target.value)} />
              </label>
              <label className="text-xs text-white/60 md:col-span-2">
                Symbols
                <input className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 text-xs" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
              </label>
              <label className="text-xs text-white/60">
                Horizons (sessions)
                <input className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 text-xs" value={horizons} onChange={(e) => setHorizons(e.target.value)} />
              </label>
            </div>
            <button
              disabled={busy}
              className="mt-3 rounded-md bg-sky-500/20 px-3 py-1.5 text-xs text-sky-200 hover:bg-sky-500/30 disabled:opacity-50"
              onClick={() =>
                void run(async () => {
                  const hs = horizons.split(',').map((h) => parseInt(h.trim(), 10)).filter((n) => Number.isFinite(n));
                  setEvaluation(await factorsClient.evaluate({ expression, symbols: symbolList(), horizons: hs }));
                })
              }
            >
              {busy ? 'Running…' : 'Run evaluation'}
            </button>
          </div>

          {evaluation && (
            <>
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                <Metric label="Mean IC" value={fmt(evaluation.ic.summary.meanIC)} />
                <Metric label="Mean Rank IC" value={fmt(evaluation.rankIC.summary.meanIC)} />
                <Metric label="IC IR" value={fmt(evaluation.ic.summary.informationRatio, 3)} />
                <Metric label="IC t-stat (HAC)" value={fmt(evaluation.ic.summary.hac?.tStatistic, 3)} />
                <Metric label="IC p-value" value={fmt(evaluation.ic.summary.hac?.pValue, 4)} />
                <Metric label="Coverage" value={`${(evaluation.coverage * 100).toFixed(1)}%`} />
              </div>
              <div className="glass-card rounded-xl p-4">
                <h3 className="mb-2 text-xs font-medium">IC time series ({evaluation.observations} obs, {evaluation.symbols.length} symbols)</h3>
                <div className="text-sky-300">
                  <Sparkline values={evaluation.ic.series} />
                </div>
              </div>
              <div className="glass-card rounded-xl p-4">
                <h3 className="mb-2 text-xs font-medium">Factor decay</h3>
                <table className="w-full text-left text-xs">
                  <thead className="text-white/40">
                    <tr><th className="py-1">Horizon</th><th>Mean IC</th><th>IR</th><th>Hit rate</th><th>Periods</th></tr>
                  </thead>
                  <tbody>
                    {evaluation.decay.curve.map((p) => (
                      <tr key={p.horizon} className="border-t border-white/5">
                        <td className="py-1">{p.horizon}</td>
                        <td>{fmt(p.meanIC)}</td>
                        <td>{fmt(p.informationRatio, 3)}</td>
                        <td>{fmt(p.hitRate, 3)}</td>
                        <td>{p.validPeriods ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {evaluation.warnings.length > 0 && (
                <div className="glass-card-subtle rounded-lg p-3 text-xs text-amber-200/80">
                  {evaluation.warnings.slice(0, 4).map((w) => <div key={w}>{w}</div>)}
                </div>
              )}
            </>
          )}
        </section>
      )}

      {tab === 'portfolio' && (
        <section className="space-y-4">
          <div className="glass-card rounded-xl p-4">
            <div className="grid gap-3 md:grid-cols-4">
              <label className="text-xs text-white/60">
                Formula
                <input className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 font-mono text-xs" value={expression} onChange={(e) => setExpression(e.target.value)} />
              </label>
              <label className="text-xs text-white/60 md:col-span-3">
                Symbols
                <input className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 text-xs" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
              </label>
              <label className="text-xs text-white/60">
                Quantiles
                <input type="number" className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 text-xs" value={quantiles} onChange={(e) => setQuantiles(parseInt(e.target.value, 10) || 5)} />
              </label>
              <label className="text-xs text-white/60">
                Rebalance (sessions)
                <input type="number" className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 text-xs" value={rebalance} onChange={(e) => setRebalance(parseInt(e.target.value, 10) || 1)} />
              </label>
              <label className="text-xs text-white/60">
                Cost (bps)
                <input type="number" className="mt-1 w-full rounded-md bg-black/30 px-2 py-1.5 text-xs" value={costBps} onChange={(e) => setCostBps(parseFloat(e.target.value) || 0)} />
              </label>
            </div>
            <button
              disabled={busy}
              className="mt-3 rounded-md bg-sky-500/20 px-3 py-1.5 text-xs text-sky-200 hover:bg-sky-500/30 disabled:opacity-50"
              onClick={() =>
                void run(async () =>
                  setPortfolio(
                    await factorsClient.portfolio({
                      expression,
                      symbols: symbolList(),
                      quantiles,
                      longShort: true,
                      rebalance,
                      costBps,
                      weighting: 'equal',
                    }),
                  ),
                )
              }
            >
              {busy ? 'Simulating…' : 'Run simulation'}
            </button>
          </div>

          {portfolio && (
            <>
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                <Metric label="Net total return" value={fmt(portfolio.longShortMetrics?.totalReturn, 4)} />
                <Metric label="Gross total return" value={fmt(portfolio.grossLongShortMetrics?.totalReturn, 4)} />
                <Metric label="Sharpe (net)" value={fmt(portfolio.longShortMetrics?.sharpe, 3)} />
                <Metric label="Max drawdown" value={fmt(portfolio.longShortMetrics?.maxDrawdown, 4)} />
                <Metric label="Avg turnover" value={fmt(portfolio.turnover.average, 3)} />
                <Metric label="Total cost" value={fmt(portfolio.cost.totalCost, 4)} />
              </div>
              <div className="glass-card rounded-xl p-4">
                <h3 className="mb-2 text-xs font-medium">Quantile mean period returns</h3>
                <table className="w-full text-left text-xs">
                  <thead className="text-white/40">
                    <tr><th className="py-1">Quantile</th><th>Total return</th><th>Sharpe</th><th>Max DD</th><th>Hit rate</th></tr>
                  </thead>
                  <tbody>
                    {Object.entries(portfolio.quantileMetrics).map(([q, m]) => (
                      <tr key={q} className="border-t border-white/5">
                        <td className="py-1">{q}</td>
                        <td>{fmt(m.totalReturn, 4)}</td>
                        <td>{fmt(m.sharpe, 3)}</td>
                        <td>{fmt(m.maxDrawdown, 4)}</td>
                        <td>{fmt(m.hitRate, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="glass-card rounded-xl p-4">
                <h3 className="mb-2 text-xs font-medium">Final long-short weights (top {Math.min(10, portfolio.finalWeights.length)})</h3>
                <div className="flex flex-wrap gap-1 text-[11px]">
                  {portfolio.finalWeights.slice(0, 10).map((w) => (
                    <span key={w.instrument} className={cn('rounded px-1.5 py-0.5', w.weight >= 0 ? 'bg-emerald-500/15 text-emerald-200' : 'bg-red-500/15 text-red-200')}>
                      #{w.instrument} {w.weight.toFixed(3)}
                    </span>
                  ))}
                  {portfolio.finalWeights.length === 0 && <span className="text-white/40">no positions formed</span>}
                </div>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}

export default FactorLabScreen;
