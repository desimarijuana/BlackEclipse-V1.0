'use client';

// ── Portfolio stress lab ────────────────────────────────────────────────────
// A small expert surface over the deterministic risk model: weights + a
// covariance (or a return matrix) -> volatility, VaR/ES and scenario P&L.
// Nothing is computed in the browser and no sample data is invented.

import React, { useCallback, useState } from 'react';
import {
  backtestClient,
  type StressEnvelope,
} from '@/lib/backtest/backtest-client';
import { Activity, Loader2 } from '@/lib/icons';

function parseJson<T>(text: string, fallback: T): T {
  if (!text.trim()) return fallback;
  return JSON.parse(text) as T;
}

export interface PortfolioStressLabProps {
  symbols?: string[];
  onError?: (message: string | null) => void;
}

export function PortfolioStressLab({ symbols = [], onError }: PortfolioStressLabProps) {
  const [weightsText, setWeightsText] = useState('0.6, 0.4');
  const [covText, setCovText] = useState('');
  const [scenarioText, setScenarioText] = useState('');
  const [result, setResult] = useState<StressEnvelope | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    onError?.(null);
    try {
      const weights = weightsText.split(',').map((v) => Number(v.trim())).filter((v) => Number.isFinite(v));
      const covariance = parseJson<number[][] | null>(covText, null);
      const scenarios = parseJson<Record<string, unknown> | null>(scenarioText, null);
      if (!weights.length) throw new Error('enter at least one weight');
      const payload: Record<string, unknown> = { weights };
      if (covariance) payload.covariance = covariance;
      if (scenarios) payload.scenarios = scenarios;
      if (symbols.length === weights.length) payload.symbols = symbols;
      if (!covariance && !scenarios) throw new Error('paste a covariance matrix or a scenario map');
      setResult(await backtestClient.stress(payload));
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'stress failed');
    } finally {
      setBusy(false);
    }
  }, [busy, weightsText, covText, scenarioText, symbols, onError]);

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Activity className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Portfolio stress</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          VaR · ES · scenario P&L
        </span>
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy}
          className="glass-card-subtle ml-auto inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null} Run
        </button>
      </div>

      <div className="grid gap-2 lg:grid-cols-3">
        <label className="block text-[11px] text-muted-foreground">
          Weights (comma separated)
          <input
            value={weightsText}
            onChange={(e) => setWeightsText(e.target.value)}
            className="glass-card-subtle mt-1 w-full rounded-lg px-2 py-1.5 font-mono text-xs"
          />
        </label>
        <label className="block text-[11px] text-muted-foreground lg:col-span-2">
          Covariance matrix (JSON, optional)
          <textarea
            value={covText}
            onChange={(e) => setCovText(e.target.value)}
            rows={2}
            placeholder='[[0.04,0.01],[0.01,0.0225]]'
            className="glass-card-subtle mt-1 w-full rounded-lg px-2 py-1.5 font-mono text-[11px]"
          />
        </label>
        <label className="block text-[11px] text-muted-foreground lg:col-span-3">
          Scenarios (JSON, optional)
          <textarea
            value={scenarioText}
            onChange={(e) => setScenarioText(e.target.value)}
            rows={2}
            placeholder='{"equity -20%": {"SPY": -0.2, "TLT": 0.05}}'
            className="glass-card-subtle mt-1 w-full rounded-lg px-2 py-1.5 font-mono text-[11px]"
          />
        </label>
      </div>

      {result ? (
        <div className="mt-3 grid gap-2 text-[11px] sm:grid-cols-3">
          {result.parametric ? (
            <Card
              title="Parametric"
              lines={[
                `Vol ${(result.parametric.volatility * 100).toFixed(2)}%`,
                `VaR ${(result.parametric.varPct * 100).toFixed(2)}%`,
                `ES ${(result.parametric.expectedShortfallPct * 100).toFixed(2)}%`,
              ]}
            />
          ) : null}
          {result.historical ? (
            <Card
              title="Historical"
              lines={[
                `VaR ${(result.historical.varPct * 100).toFixed(2)}%`,
                `ES ${(result.historical.expectedShortfallPct * 100).toFixed(2)}%`,
                `${result.historical.observations} obs`,
              ]}
            />
          ) : null}
          {result.scenario?.worst ? (
            <Card
              title="Worst scenario"
              lines={[
                result.scenario.worst.name,
                `${(result.scenario.worst.pnlPct * 100).toFixed(2)}%`,
                `${result.scenario.scenarios[0]?.uncoveredSymbols.length ?? 0} uncovered`,
              ]}
            />
          ) : null}
        </div>
      ) : (
        <p className="mt-3 text-[11px] text-muted-foreground">
          Paste a covariance matrix or scenario map. Missing inputs are refused, never assumed.
        </p>
      )}
    </div>
  );
}

function Card({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="rounded-xl border border-white/5 bg-black/10 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{title}</p>
      {lines.map((line) => <p key={line} className="mt-0.5 font-mono">{line}</p>)}
    </div>
  );
}
