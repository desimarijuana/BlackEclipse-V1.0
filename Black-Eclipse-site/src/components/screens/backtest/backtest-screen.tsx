'use client';

// ── Backtest screen — the quant research workspace ───────────────────────────
// Configure a strategy, run a deterministic backtest over real historical data
// (via the Python Quant Engine), and inspect metrics, equity/drawdown curves,
// trades and execution assumptions. Every displayed number comes from the
// runtime's result artifact — an empty result is shown honestly, never faked.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import type { EChartsOption } from 'echarts';
import { useEChart, baseChartOption } from '@/components/screens/portfolio/use-echart';
import { useBacktestScreen } from '@/lib/backtest/use-backtest-screen';
import { ResearchPanel } from './research-panel';

const StrategyCanvas = dynamic(
  () => import('./strategy-canvas').then((m) => m.StrategyCanvas),
  { ssr: false, loading: () => <div className="glass-card rounded-2xl p-6 text-xs text-muted-foreground">Loading builder…</div> },
);
const PythonLab = dynamic(
  () => import('./python-lab').then((m) => m.PythonLab),
  { ssr: false, loading: () => <div className="glass-card rounded-2xl p-6 text-xs text-muted-foreground">Loading lab…</div> },
);
import {
  backtestClient,
  formatMetric,
  type BacktestResult,
  type ExperimentSummary,
  type StrategyRecord,
  type VersionDiff,
  type VersionInfo,
} from '@/lib/backtest/backtest-client';
import {
  Activity, AlertTriangle, Download, History, LineChart, Loader2, Play, Plus, RefreshCw,
  Trash2, TrendingUp, Upload,
} from '@/lib/icons';
import { cn } from '@/lib/utils';

const SAMPLE_STRATEGY = {
  strategy: { id: 'ema_cross_demo', name: 'EMA Cross (demo)', version: '1.0.0' },
  universe: { asset_classes: ['crypto'], symbols: ['BTC-USD'] },
  timeframes: { primary: '1d' },
  indicators: [
    { id: 'ema_fast', type: 'ema', params: { period: 12 } },
    { id: 'ema_slow', type: 'ema', params: { period: 50 } },
    { id: 'atr', type: 'atr', params: { period: 14 } },
  ],
  rules: {
    entry: { long: { conditions: [
      { left: { ref: 'ema_fast' }, op: 'cross_above', right: { ref: 'ema_slow' } },
    ] } },
    exit: {
      long: { conditions: [
        { left: { ref: 'ema_fast' }, op: 'cross_below', right: { ref: 'ema_slow' } },
      ] },
      stop_loss: { type: 'atr', value: 2.0 },
      take_profit: { type: 'risk_reward', value: 2.0 },
    },
  },
  position_sizing: { type: 'percent_equity', value: 90 },
  risk: { max_position_pct: 100 },
  execution: {
    commission: { type: 'percentage', value: 0.1 },
    slippage: { type: 'percentage', value: 0.05 },
    spread: { type: 'bps', value: 5 },
  },
};

const METRIC_CARDS: Array<{ key: string; label: string; icon: 'return' | 'risk' | 'ratio' }> = [
  { key: 'total_return', label: 'Total Return', icon: 'return' },
  { key: 'cagr', label: 'CAGR', icon: 'return' },
  { key: 'max_drawdown', label: 'Max Drawdown', icon: 'risk' },
  { key: 'volatility', label: 'Volatility', icon: 'risk' },
  { key: 'sharpe', label: 'Sharpe', icon: 'ratio' },
  { key: 'sortino', label: 'Sortino', icon: 'ratio' },
  { key: 'calmar', label: 'Calmar', icon: 'ratio' },
  { key: 'win_rate', label: 'Win Rate', icon: 'return' },
  { key: 'profit_factor', label: 'Profit Factor', icon: 'ratio' },
  { key: 'trade_count', label: 'Trades', icon: 'ratio' },
  { key: 'expectancy', label: 'Expectancy', icon: 'return' },
  { key: 'avg_gross_exposure', label: 'Avg Exposure', icon: 'risk' },
];

// ── Strategy portability (immutable versions · export · import · diff) ──────
// Every strategy must be reachable and portable independently of this UI: this
// panel exports the canonical IR as a checksummed bundle, imports one back, and
// diffs any two stored versions. All data comes from the Python Quant Engine.
function StrategyPortability({
  record,
  onChanged,
}: {
  record: StrategyRecord;
  onChanged: () => void;
}) {
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    backtestClient.listVersions(record.id).then((vs) => {
      if (!alive) return;
      setVersions(vs);
      setTo(record.version);
      setFrom(vs.length > 1 ? vs[0].version : '');
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [record.id, record.version]);

  const download = async () => {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const bundle = await backtestClient.getBundle(record.id, record.version);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${record.id}@${record.version}.bundle.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMsg(`Exported ${record.id} v${record.version} (sha256 ${bundle.manifest.contentHash.slice(0, 12)}…).`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'export failed');
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File) => {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const parsed = JSON.parse(await file.text()) as Record<string, unknown>;
      const outcome = await backtestClient.importStrategy(parsed, true);
      if (!outcome.valid) {
        setErr('Bundle imported but failed validation.');
        return;
      }
      setMsg(`Imported ${String((outcome.strategy as { id?: string }).id)} (sha256 ${outcome.contentHash.slice(0, 12)}…).`);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'import failed');
    } finally {
      setBusy(false);
    }
  };

  const runDiff = async () => {
    setErr(null); setDiff(null);
    try {
      setDiff(await backtestClient.diffVersions(record.id, from, to));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'diff failed');
    }
  };

  return (
    <div className="rounded-xl border border-white/10 p-2">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        <History className="h-3 w-3" /> Versions &amp; portability
      </div>
      <div className="mb-2 font-mono text-[10px] text-muted-foreground">
        {versions.length} version(s)
        {record.contentHash ? ` · ${record.contentHash.slice(0, 12)}…` : ''}
      </div>
      <div className="mb-2 flex gap-2">
        <button type="button" onClick={() => void download()} disabled={busy}
          className="glass-button flex items-center gap-1 rounded-md px-2 py-1 text-[11px] disabled:opacity-50">
          <Download className="h-3 w-3" /> Export
        </button>
        <label className="glass-button flex cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-[11px]">
          <Upload className="h-3 w-3" /> Import
          <input type="file" accept=".json,application/json" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ''; }} />
        </label>
      </div>
      {versions.length > 1 && (
        <div className="flex flex-col gap-1">
          <div className="flex gap-1">
            <select value={from} onChange={(e) => setFrom(e.target.value)}
              className="glass-card-subtle flex-1 rounded-md px-1.5 py-1 font-mono text-[10px] text-foreground outline-none">
              {versions.map((v) => <option key={v.version} value={v.version}>{v.version}</option>)}
            </select>
            <span className="self-center text-[10px] text-muted-foreground">→</span>
            <select value={to} onChange={(e) => setTo(e.target.value)}
              className="glass-card-subtle flex-1 rounded-md px-1.5 py-1 font-mono text-[10px] text-foreground outline-none">
              {versions.map((v) => <option key={v.version} value={v.version}>{v.version}</option>)}
            </select>
            <button type="button" onClick={() => void runDiff()}
              className="glass-button rounded-md px-2 py-1 text-[10px]">Diff</button>
          </div>
          {diff && (
            <div className="mt-1 font-mono text-[10px] text-muted-foreground">
              {diff.sameContent
                ? 'identical content'
                : `${diff.changeCount} change(s): ${Object.entries(diff.bySection).map(([k, n]) => `${k}×${n}`).join(', ')}`}
            </div>
          )}
        </div>
      )}
      {msg && <div className="mt-1 text-[10px] text-emerald-400">{msg}</div>}
      {err && <div className="mt-1 text-[10px] text-amber-400">{err}</div>}
    </div>
  );
}

function EquityChart({ result }: { result: BacktestResult }) {
  const deps = useMemo(() => [result.equityCurve, result.drawdownCurve], [result]);
  const ref = useEChart((): EChartsOption => {
    const option = baseChartOption();
    const x = result.equityCurve.map((p) => p.ts ?? String(p.index));
    return {
      ...option,
      grid: { left: 56, right: 16, top: 24, bottom: 40 },
      xAxis: { type: 'category', data: x, axisLabel: { color: '#9ca3af', fontSize: 10 }, boundaryGap: false },
      yAxis: { type: 'value', scale: true, axisLabel: { color: '#9ca3af', fontSize: 10 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
      series: [{
        name: 'Equity', type: 'line', showSymbol: false, smooth: false,
        data: result.equityCurve.map((p) => p.equity),
        lineStyle: { color: '#22d3ee', width: 2 }, itemStyle: { color: '#22d3ee' },
        areaStyle: { color: 'rgba(34,211,238,0.12)' },
      }],
    } as EChartsOption;
  }, deps);
  return <div ref={ref} className="h-[260px] w-full" />;
}

function DrawdownChart({ result }: { result: BacktestResult }) {
  const deps = useMemo(() => [result.drawdownCurve], [result]);
  const ref = useEChart((): EChartsOption => {
    const option = baseChartOption();
    const x = result.drawdownCurve.map((p) => p.ts ?? String(p.index));
    return {
      ...option,
      grid: { left: 56, right: 16, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: x, axisLabel: { color: '#9ca3af', fontSize: 10 }, boundaryGap: false },
      yAxis: { type: 'value', axisLabel: { color: '#9ca3af', fontSize: 10, formatter: '{value}%' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
      series: [{
        name: 'Drawdown', type: 'line', showSymbol: false,
        data: result.drawdownCurve.map((p) => p.drawdown),
        lineStyle: { color: '#f87171', width: 1.5 }, itemStyle: { color: '#f87171' },
        areaStyle: { color: 'rgba(248,113,113,0.15)' },
      }],
    } as EChartsOption;
  }, deps);
  return <div ref={ref} className="h-[200px] w-full" />;
}

function TradeTable({ result }: { result: BacktestResult }) {
  if (!result.trades.length) {
    return <p className="text-xs text-muted-foreground">No trades were generated for this configuration.</p>;
  }
  return (
    <div className="max-h-[280px] overflow-auto">
      <table className="w-full text-left font-mono text-[11px]">
        <thead className="sticky top-0 bg-black/30 text-muted-foreground">
          <tr>
            <th className="px-2 py-1">Symbol</th>
            <th className="px-2 py-1">Dir</th>
            <th className="px-2 py-1">Entry</th>
            <th className="px-2 py-1">Exit</th>
            <th className="px-2 py-1 text-right">Net P&L</th>
            <th className="px-2 py-1 text-right">%</th>
            <th className="px-2 py-1">Reason</th>
          </tr>
        </thead>
        <tbody>
          {result.trades.map((t) => (
            <tr key={t.id} className="border-t border-white/5">
              <td className="px-2 py-1">{t.symbol}</td>
              <td className={cn('px-2 py-1', t.direction === 'long' ? 'text-emerald-400' : 'text-rose-400')}>
                {t.direction}
              </td>
              <td className="px-2 py-1">{t.entryPrice.toFixed(2)}</td>
              <td className="px-2 py-1">{t.exitPrice.toFixed(2)}</td>
              <td className={cn('px-2 py-1 text-right', t.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                {t.netPnl.toFixed(2)}
              </td>
              <td className="px-2 py-1 text-right">{t.pnlPct.toFixed(2)}%</td>
              <td className="px-2 py-1 text-muted-foreground">{t.exitReason || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExperimentRow({ exp, onOpen, onDelete }: {
  exp: ExperimentSummary;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg px-2 py-1 hover:bg-white/5">
      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(exp.id)}>
        <div className="truncate font-mono text-[11px] text-foreground">
          {exp.strategyId ?? exp.kind} <span className="text-muted-foreground">v{exp.strategyVersion}</span>
        </div>
        <div className="truncate font-mono text-[10px] text-muted-foreground">
          {(exp.symbols || []).join(', ')} · ret {formatMetric('total_return', exp.metrics.total_return)} ·
          sharpe {formatMetric('sharpe', exp.metrics.sharpe)}
        </div>
      </button>
      <button type="button" aria-label="Delete experiment" onClick={() => onDelete(exp.id)}
        className="shrink-0 rounded p-1 text-muted-foreground hover:text-rose-400">
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function BacktestScreen() {
  const state = useBacktestScreen();
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorText, setEditorText] = useState(() => JSON.stringify(SAMPLE_STRATEGY, null, 2));
  const [description, setDescription] = useState('');
  const [symbols, setSymbols] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [capital, setCapital] = useState(100000);
  const [commission, setCommission] = useState(0.1);
  const [slippage, setSlippage] = useState(0.05);
  const [spread, setSpread] = useState(5);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [bgMode, setBgMode] = useState(true);
  const [mode, setMode] = useState<'form' | 'visual' | 'python'>('form');

  useEffect(() => {
    if (state.selected) {
      const specs = state.selected.spec as { universe?: { symbols?: string[] } };
      if (!symbols && specs.universe?.symbols?.length) setSymbols(specs.universe.symbols.join(', '));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.selected]);

  const parseSpec = useCallback((): Record<string, unknown> | null => {
    if (editorOpen) {
      try {
        return JSON.parse(editorText) as Record<string, unknown>;
      } catch (err) {
        setFormError(err instanceof Error ? err.message : 'invalid JSON');
        return null;
      }
    }
    if (state.selected) return JSON.parse(JSON.stringify(state.selected.spec)) as Record<string, unknown>;
    setFormError('Select a strategy or open the editor to define one.');
    return null;
  }, [editorOpen, editorText, state.selected]);

  const applyCosts = (spec: Record<string, unknown>): Record<string, unknown> => {
    const exec = (spec.execution as Record<string, unknown>) ?? {};
    spec.execution = {
      ...exec,
      commission: { type: 'percentage', value: commission },
      slippage: { type: 'percentage', value: slippage },
      spread: { type: 'bps', value: spread },
    };
    return spec;
  };

  const handleRun = useCallback(async () => {
    setFormError(null);
    setNotice(null);
    const spec = parseSpec();
    if (!spec) return;
    applyCosts(spec);
    const syms = symbols.split(',').map((s) => s.trim().toUpperCase()).filter(Boolean);
    const result = await state.run({
      strategy: spec,
      symbols: syms.length ? syms : undefined,
      start: start || undefined,
      end: end || undefined,
      initialCapital: capital,
      save: true,
      background: bgMode,
    });
    if (result && result.status === 'OK' && !result.trades.length) {
      setNotice('The run completed with no trades (check history length, warm-up and rule thresholds).');
    }
  }, [parseSpec, symbols, start, end, capital, commission, slippage, spread, state, bgMode]);

  const handleSave = useCallback(async () => {
    setFormError(null);
    try {
      const parsed = JSON.parse(editorText) as Record<string, unknown>;
      await state.saveStrategy(parsed, description || undefined);
      setNotice('Strategy saved.');
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'save failed');
    }
  }, [editorText, description, state]);

  const result = state.result;

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-4">
      <div className="glass-card flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
        <span className="h-6 w-1 shrink-0 rounded-full bg-primary" />
        <div className="min-w-0 flex-1">
          <h1 className="font-serif text-xl font-semibold tracking-tight text-foreground">Backtest</h1>
          <p className="font-mono text-[10px] text-muted-foreground">
            Deterministic quant engine · {state.strategies.length} strategies · {state.experiments.length} experiments
          </p>
        </div>
        <button type="button" onClick={() => setMode((m) => (m === 'visual' ? 'form' : 'visual'))}
          className={cn('glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs',
            mode === 'visual' && 'text-sky-300')}>
          {mode === 'visual' ? 'Form' : 'Visual builder'}
        </button>
        <button type="button" onClick={() => setMode((m) => (m === 'python' ? 'form' : 'python'))}
          className={cn('glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs',
            mode === 'python' && 'text-sky-300')}>
          Python lab
        </button>
        <button type="button" onClick={() => void state.refresh()}
          className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs">
          <RefreshCw className={cn('h-3.5 w-3.5', state.loading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {state.error && (
        <div className="glass-card-subtle flex items-start gap-2 rounded-xl border border-rose-500/30 px-3 py-2 text-xs text-rose-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{state.error}</span>
        </div>
      )}
      {formError && (
        <div className="glass-card-subtle flex items-start gap-2 rounded-xl border border-amber-500/30 px-3 py-2 text-xs text-amber-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{formError}</span>
        </div>
      )}
      {notice && !state.error && (
        <div className="glass-card-subtle rounded-xl px-3 py-2 text-xs text-muted-foreground">{notice}</div>
      )}

      {mode === 'visual' && (
        <StrategyCanvas onSaved={(id) => {
          setMode('form');
          setNotice(`Compiled and saved strategy ${id}.`);
          void state.refresh();
          void state.selectStrategy(id);
        }} />
      )}
      {mode === 'python' && (
        <PythonLab onResult={(result) => { state.loadResult(result); setNotice('Python strategy run complete.'); }} />
      )}

      <div className={cn('grid grid-cols-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)]', mode !== 'form' && 'hidden')}>
        {/* ── Control panel ── */}
        <div className="glass-card flex flex-col gap-3 rounded-2xl p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">Configuration</h2>
            <button type="button" onClick={() => setEditorOpen((v) => !v)}
              className="glass-button rounded-md px-2 py-1 text-[11px]">
              {editorOpen ? 'Use saved' : 'Edit spec'}
            </button>
          </div>

          {!editorOpen && (
            <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
              Strategy
              <select
                value={state.selectedId ?? ''}
                onChange={(e) => void state.selectStrategy(e.target.value || null)}
                className="glass-card-subtle rounded-lg px-2 py-1.5 text-xs text-foreground outline-none"
              >
                <option value="">— select a strategy —</option>
                {state.strategies.map((s) => (
                  <option key={s.id} value={s.id}>{s.name} ({s.id} v{s.latestVersion})</option>
                ))}
              </select>
            </label>
          )}

          {editorOpen && (
            <>
              <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
                Strategy JSON
                <textarea
                  value={editorText}
                  onChange={(e) => setEditorText(e.target.value)}
                  spellCheck={false}
                  className="h-[220px] w-full resize-y rounded-lg border border-white/10 bg-black/30 p-2 font-mono text-[10px] text-foreground outline-none"
                />
              </label>
              <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
                Description (optional)
                <input value={description} onChange={(e) => setDescription(e.target.value)}
                  className="glass-card-subtle rounded-lg px-2 py-1.5 text-xs text-foreground outline-none" />
              </label>
              <div className="flex gap-2">
                <button type="button" onClick={() => void handleSave()}
                  className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs">
                  <Plus className="h-3.5 w-3.5" /> Save strategy
                </button>
              </div>
            </>
          )}

          {state.selected && (
            <StrategyPortability
              record={state.selected}
              onChanged={() => { void state.refresh(); }}
            />
          )}

          <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
            Symbols (comma separated; blank = strategy universe)
            <input value={symbols} onChange={(e) => setSymbols(e.target.value)}
              placeholder="BTC-USD, ETH-USD"
              className="glass-card-subtle rounded-lg px-2 py-1.5 font-mono text-xs text-foreground outline-none" />
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
              Start
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
                className="glass-card-subtle rounded-lg px-2 py-1.5 text-xs text-foreground outline-none" />
            </label>
            <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
              End
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
                className="glass-card-subtle rounded-lg px-2 py-1.5 text-xs text-foreground outline-none" />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
            Initial capital
            <input type="number" value={capital} min={1}
              onChange={(e) => setCapital(Number(e.target.value) || 0)}
              className="glass-card-subtle rounded-lg px-2 py-1.5 font-mono text-xs text-foreground outline-none" />
          </label>

          <div className="rounded-xl border border-white/10 p-2">
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Execution costs</div>
            <div className="grid grid-cols-3 gap-2">
              <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
                Comm %
                <input type="number" step="0.01" value={commission}
                  onChange={(e) => setCommission(Number(e.target.value) || 0)}
                  className="glass-card-subtle rounded-md px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
              </label>
              <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
                Slip %
                <input type="number" step="0.01" value={slippage}
                  onChange={(e) => setSlippage(Number(e.target.value) || 0)}
                  className="glass-card-subtle rounded-md px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
              </label>
              <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
                Spread bps
                <input type="number" step="0.1" value={spread}
                  onChange={(e) => setSpread(Number(e.target.value) || 0)}
                  className="glass-card-subtle rounded-md px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
              </label>
            </div>
          </div>

          <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <input type="checkbox" checked={bgMode} onChange={(e) => setBgMode(e.target.checked)} />
            Run in background (poll progress)
          </label>
          <button type="button" onClick={() => void handleRun()} disabled={state.running}
            className="glass-button-add flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50">
            {state.running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {state.running
              ? `Running…${state.progress ? ` ${Math.round(state.progress.percent)}%` : ''}`
              : 'Run backtest'}
          </button>

          <div className="rounded-xl border border-white/10 p-2">
            <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
              <Activity className="h-3 w-3" /> Capabilities
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 font-mono text-[10px]">
              {Object.entries(state.capabilities).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <span className="text-muted-foreground">{k}</span>
                  <span className={cn(
                    v === 'available' && 'text-emerald-400',
                    v === 'partial' && 'text-amber-400',
                    v === 'unsupported' && 'text-muted-foreground',
                  )}>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Results ── */}
        <div className="flex min-w-0 flex-col gap-4">
          {!result && (
            <div className="glass-card flex min-h-[300px] flex-col items-center justify-center gap-2 rounded-2xl p-8 text-center">
              <LineChart className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Configure a strategy and run a backtest to see performance, risk and trades.
              </p>
            </div>
          )}

          {result && (
            <>
              <div className="glass-card rounded-2xl p-4">
                <div className="mb-3 flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  <h2 className="text-sm font-semibold text-foreground">Performance</h2>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {String((result.metadata.symbols as string[])?.join(', '))} ·{' '}
                    {String(result.metadata.interval)} · {String(result.observability.barsProcessed)} bars
                    {result.experimentId ? ` · ${result.experimentId}` : ''}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                  {METRIC_CARDS.map((c) => (
                    <MetricCardWrapper key={c.key} name={c.key} label={c.label} value={result.metrics[c.key]} />
                  ))}
                </div>
              </div>

              <div className="glass-card rounded-2xl p-4">
                <h3 className="mb-2 text-xs font-semibold text-foreground">Equity Curve</h3>
                <EquityChart result={result} />
              </div>

              <div className="glass-card rounded-2xl p-4">
                <h3 className="mb-2 text-xs font-semibold text-foreground">Drawdown</h3>
                <DrawdownChart result={result} />
              </div>

              <div className="glass-card rounded-2xl p-4">
                <h3 className="mb-2 text-xs font-semibold text-foreground">
                  Trades <span className="text-muted-foreground">({result.trades.length})</span>
                </h3>
                <TradeTable result={result} />
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="glass-card rounded-2xl p-4">
                  <h3 className="mb-2 text-xs font-semibold text-foreground">Execution assumptions</h3>
                  <pre className="max-h-[200px] overflow-auto rounded-lg bg-black/30 p-2 font-mono text-[10px] text-muted-foreground">
                    {JSON.stringify(result.configuration.execution ?? {}, null, 2)}
                  </pre>
                </div>
                <div className="glass-card rounded-2xl p-4">
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <AlertTriangle className="h-3.5 w-3.5" /> Warnings
                    <span className="text-muted-foreground">({result.warnings.length})</span>
                  </h3>
                  {result.warnings.length === 0 ? (
                    <p className="text-[11px] text-muted-foreground">No warnings.</p>
                  ) : (
                    <ul className="max-h-[200px] space-y-1 overflow-auto">
                      {result.warnings.map((w, i) => (
                        <li key={i} className="font-mono text-[10px] text-muted-foreground">
                          <span className="text-amber-400">{w.code}</span>: {w.message}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </>
          )}

          <ResearchPanel
            selected={state.selected}
            running={state.running}
            research={state.research}
            progress={state.progress}
            onRun={state.runResearch}
            onError={setFormError}
          />

          <div className="glass-card rounded-2xl p-4">
            <div className="mb-2 flex items-center gap-2">
              <LineChart className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold text-foreground">Experiments</h2>
            </div>
            {state.experiments.length === 0 ? (
              <p className="text-xs text-muted-foreground">No experiments yet.</p>
            ) : (
              <div className="space-y-0.5">
                {state.experiments.map((exp) => (
                  <ExperimentRow key={exp.id} exp={exp}
                    onOpen={(id) => void state.openExperiment(id)}
                    onDelete={(id) => void state.removeExperiment(id)} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCardWrapper({ name, label, value }: { name: string; label: string; value: number | null | undefined }) {
  return (
    <div className="glass-card-subtle rounded-xl px-3 py-2" data-metric={name}>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn(
        'font-mono text-sm text-foreground',
        name.includes('drawdown') && value != null && value < 0 && 'text-rose-400',
        name.includes('return') && value != null && value < 0 && 'text-rose-400',
        name.includes('return') && value != null && value > 0 && 'text-emerald-400',
      )}>
        {formatMetric(name, value)}
      </div>
    </div>
  );
}
