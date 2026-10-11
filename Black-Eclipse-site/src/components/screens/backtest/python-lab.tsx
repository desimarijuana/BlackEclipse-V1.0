'use client';

// ── Python Strategy Lab ──────────────────────────────────────────────────────
// A focused code surface for the Python Strategy SDK. The user writes a
// `Strategy` subclass; "Run" sends the source to the managed, isolated runtime
// (`/quant/python/run`), which executes it in a separate, env-scrubbed,
// time-limited process and returns the SAME BacktestResult as any other path.
// No code is evaluated in the browser, and this UI never computes signals.

import React, { useState } from 'react';
import { backtestClient, formatMetric, type BacktestResult } from '@/lib/backtest/backtest-client';
import { Loader2, Play } from '@/lib/icons';
import { cn } from '@/lib/utils';

const SAMPLE = `from harness.quant.sdk import Strategy

class MyStrategy(Strategy):
    name = "my_strategy"

    def initialize(self, ctx):
        ctx.declare_indicator("fast", "ema", {"period": 12})
        ctx.declare_indicator("slow", "ema", {"period": 50})
        ctx.declare_indicator("atr", "atr", {"period": 14})
        ctx.set_stop_loss("atr", 2.0, atr_indicator="atr")
        ctx.set_take_profit("risk_reward", 2.0)

    def on_data(self, ctx, bar):
        fast, slow = ctx.indicator("fast"), ctx.indicator("slow")
        if fast is None or slow is None:
            return
        if ctx.position().is_flat and fast > slow:
            ctx.buy(weight=0.9, reason="ema cross up")
        elif not ctx.position().is_flat and fast < slow:
            ctx.close(reason="ema cross down")
`;

const SUMMARY_METRICS = ['total_return', 'cagr', 'max_drawdown', 'sharpe', 'win_rate', 'trade_count'];

export function PythonLab({
  onResult,
}: {
  onResult?: (result: BacktestResult) => void;
}) {
  const [code, setCode] = useState(SAMPLE);
  const [symbols, setSymbols] = useState('BTC-USD');
  const [capital, setCapital] = useState(100000);
  const [timeoutS, setTimeoutS] = useState(60);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const run = async () => {
    setBusy(true); setError(null); setMsg(null); setResult(null);
    try {
      const raw = await backtestClient.runPythonStrategy({
        strategyCode: code,
        symbols: symbols.split(',').map((s) => s.trim()).filter(Boolean),
        initialCapital: capital,
        timeoutSeconds: timeoutS,
        save: true,
      });
      if ('runId' in raw) {
        setMsg('Run submitted in the background.');
        return;
      }
      if ('error' in raw) {
        setError(String((raw.error as { message?: string })?.message ?? 'strategy failed'));
        return;
      }
      setResult(raw as BacktestResult);
      setMsg('Run complete.');
      onResult?.(raw as BacktestResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'run failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-2 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="glass-card flex flex-col gap-2 rounded-2xl p-3">
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
            Symbols
            <input value={symbols} onChange={(e) => setSymbols(e.target.value)}
              className="glass-card-subtle w-40 rounded-md px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
          </label>
          <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
            Capital
            <input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value) || 0)}
              className="glass-card-subtle w-28 rounded-md px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
          </label>
          <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
            Timeout (s)
            <input type="number" value={timeoutS} onChange={(e) => setTimeoutS(Number(e.target.value) || 1)}
              className="glass-card-subtle w-20 rounded-md px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
          </label>
          <button type="button" onClick={() => void run()} disabled={busy}
            className="glass-button-add flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Run
          </button>
        </div>
        <textarea value={code} onChange={(e) => setCode(e.target.value)} spellCheck={false}
          className="h-[440px] w-full resize-y rounded-lg border border-white/10 bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-foreground outline-none" />
        {msg && <div className="text-[11px] text-emerald-400">{msg}</div>}
        {error && <div className="glass-card-subtle rounded-lg px-2 py-1.5 text-[11px] text-amber-400">{error}</div>}
      </div>

      <div className="glass-card flex flex-col gap-2 rounded-2xl p-3">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Result</div>
        {!result && <div className="text-[11px] text-muted-foreground">Run a strategy to see metrics.</div>}
        {result && (
          <>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              {SUMMARY_METRICS.map((k) => (
                <div key={k} className="flex items-baseline justify-between gap-2 text-[11px]">
                  <span className="text-muted-foreground">{k.replace(/_/g, ' ')}</span>
                  <span className={cn('font-mono text-foreground',
                    k.includes('return') && (result.metrics[k] ?? 0) < 0 && 'text-rose-400')}>
                    {formatMetric(k, result.metrics[k])}
                  </span>
                </div>
              ))}
            </div>
            {result.warnings?.length > 0 && (
              <div className="mt-1 border-t border-white/10 pt-1">
                <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Warnings</div>
                {result.warnings.slice(0, 8).map((w, i) => (
                  <div key={i} className="text-[10px] text-amber-400"><span className="font-mono">{w.code}</span></div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
