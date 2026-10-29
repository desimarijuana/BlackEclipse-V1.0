'use client';

// ── Portfolio backtest ──────────────────────────────────────────────────────
// Run several SAVED strategies together over one shared window. The runtime
// requires one primary timeframe across them, and the result is the same
// deterministic artifact the single-strategy panels already render.
//
// This is a portfolio of strategies, not a basket of symbols for one strategy.

import React, { useEffect, useState } from 'react';
import type {
  BacktestResult,
  PortfolioBacktestInput,
  StrategySummary,
} from '@/lib/backtest/backtest-client';
import { Layers2, Loader2, Play } from '@/lib/icons';

export function PortfolioPanel({
  strategies,
  currentId,
  start,
  end,
  capital,
  running,
  onRun,
  onError,
}: {
  strategies: StrategySummary[];
  currentId: string | null;
  start: string;
  end: string;
  capital: number;
  running: boolean;
  onRun: (input: PortfolioBacktestInput) => Promise<BacktestResult | null>;
  onError: (message: string | null) => void;
}) {
  const [selected, setSelected] = useState<string[]>(currentId ? [currentId] : []);

  useEffect(() => {
    if (!currentId) return;
    setSelected((prev) => (prev.includes(currentId) ? prev : [currentId, ...prev]));
  }, [currentId]);

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));

  const run = async () => {
    if (selected.length < 2) return;
    onError(null);
    await onRun({
      strategyIds: selected,
      start: start || undefined,
      end: end || undefined,
      initialCapital: capital,
      save: true,
      background: true,
    });
  };

  return (
    <details className="glass-card rounded-2xl p-4">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm font-semibold">
        <Layers2 className="h-4 w-4 text-primary" />
        Portfolio backtest
        <span className="font-mono text-[10px] font-normal text-muted-foreground">
          {selected.length} selected · one shared window
        </span>
      </summary>

      <div className="mt-3 flex flex-col gap-2">
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          Run two or more saved strategies together. All must share one primary timeframe; the result replaces the
          panels above and is saved as a portfolio experiment.
        </p>

        <div className="max-h-[190px] space-y-0.5 overflow-y-auto scrollbar-hide">
          {strategies.length === 0 ? (
            <p className="text-[10px] text-muted-foreground">No saved strategies yet.</p>
          ) : null}
          {strategies.map((strategy) => (
            <label
              key={strategy.id}
              className="flex items-center gap-2 rounded-lg px-2 py-1 text-[11px] hover:bg-white/5"
            >
              <input
                type="checkbox"
                checked={selected.includes(strategy.id)}
                onChange={() => toggle(strategy.id)}
              />
              <span className="min-w-0 flex-1 truncate text-foreground">
                {strategy.name || strategy.id}
              </span>
              <span className="shrink-0 font-mono text-[9px] text-muted-foreground">
                {strategy.id} · v{strategy.latestVersion}
              </span>
            </label>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void run()}
            disabled={running || selected.length < 2}
            className="glass-button-add flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
          >
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Run portfolio backtest
          </button>
          <span className="text-[9px] text-muted-foreground/60">
            {selected.length < 2 ? 'Select at least two strategies.' : `${start || '—'} → ${end || '—'}`}
          </span>
        </div>
      </div>
    </details>
  );
}
