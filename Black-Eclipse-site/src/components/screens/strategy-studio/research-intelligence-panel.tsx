'use client';

// ── Quant Research Intelligence (Strategy Studio) ───────────────────────────
// The open, horizon-wide method matrix plus the computed research figures.
// The catalog is a seed: literature extraction and quant_register_method add
// methods. Every number and every chart comes from the Python research layer.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ResponseChart } from '@/components/response/response-chart';
import type { ChartBlock } from '@/lib/response/contract';
import {
  backtestClient,
  type ResearchMethodRow,
  type ResearchSuitabilityRow,
} from '@/lib/backtest/backtest-client';
import { FlaskConical, Loader2, RefreshCw } from '@/lib/icons';

const HORIZONS = ['intraday', 'swing', 'position', 'long-term'] as const;

export interface ResearchIntelligencePanelProps {
  symbol: string;
  interval: string;
  onError?: (message: string | null) => void;
}

export function ResearchIntelligencePanel({ symbol, interval, onError }: ResearchIntelligencePanelProps) {
  const [matrix, setMatrix] = useState<Record<string, ResearchMethodRow[]>>({});
  const [total, setTotal] = useState(0);
  const [objective, setObjective] = useState('forecast volatility');
  const [horizon, setHorizon] = useState<string>('swing');
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ResearchSuitabilityRow[]>([]);
  const [blocks, setBlocks] = useState<ChartBlock[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [query, setQuery] = useState('volatility forecasting');
  const [papers, setPapers] = useState<Array<Record<string, unknown>>>([]);
  const [extracted, setExtracted] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setBusy('load');
    onError?.(null);
    try {
      const result = await backtestClient.researchMatrix();
      setMatrix(result.matrix ?? {});
      setTotal(result.total ?? 0);
      const first = Object.values(result.matrix ?? {}).flat()[0];
      if (first && selected.length === 0) setSelected([first.methodId]);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'could not load the research matrix');
    } finally {
      setBusy(null);
    }
  }, [onError, selected.length]);

  useEffect(() => { void load(); }, [load]);

  const search = useCallback(async () => {
    setBusy('search');
    onError?.(null);
    try {
      const result = await backtestClient.researchSearch({
        objective: query, instrument: symbol, timeframe: interval, limit: 8,
      });
      setPapers(result.literature ?? []);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'search failed');
    } finally {
      setBusy(null);
    }
  }, [interval, onError, query, symbol]);

  const extract = useCallback(async (paper: Record<string, unknown>) => {
    setBusy('extract');
    onError?.(null);
    try {
      const result = await backtestClient.researchExtract({
        literatureId: paper.id,
        url: paper.pdfUrl ?? paper.url,
        persist: true,
      });
      setExtracted(result);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'extraction failed');
    } finally {
      setBusy(null);
    }
  }, [onError]);

  const allMethods = useMemo(() => {
    const seen = new Set<string>();
    const rows: ResearchMethodRow[] = [];
    for (const list of Object.values(matrix)) {
      for (const row of list) {
        if (!seen.has(row.methodId)) {
          seen.add(row.methodId);
          rows.push(row);
        }
      }
    }
    return rows.sort((a, b) => a.name.localeCompare(b.name));
  }, [matrix]);

  const toggle = (methodId: string) => {
    setSelected((current) =>
      current.includes(methodId)
        ? current.filter((id) => id !== methodId)
        : [...current, methodId].slice(0, 8),
    );
  };

  const compare = useCallback(async () => {
    if (selected.length === 0) return;
    setBusy('compare');
    onError?.(null);
    try {
      const result = await backtestClient.researchCompare({
        methodIds: selected,
        objective,
        horizon,
        instrument: symbol,
        availableData: ['returns', 'price_series', 'realized_variance'],
      });
      setComparison(result.comparison ?? []);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'comparison failed');
    } finally {
      setBusy(null);
    }
  }, [objective, onError, selected, symbol, horizon]);

  const visualize = useCallback(async () => {
    setBusy('visualize');
    onError?.(null);
    try {
      const result = await backtestClient.researchVisualize({
        methodIds: selected,
        objective,
        horizon,
        instrument: symbol,
        symbol,
        interval,
        loadData: true,
      });
      setBlocks(result.blocks ?? []);
    } catch (e) {
      onError?.(e instanceof Error ? e.message : 'figure build failed');
    } finally {
      setBusy(null);
    }
  }, [interval, objective, onError, selected, symbol, horizon]);

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FlaskConical className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Research intelligence</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          sources · methods · reproduction · figures
        </span>
        <button
          type="button"
          onClick={() => void load()}
          className="ml-auto inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-[11px]"
        >
          <RefreshCw className={`h-3 w-3 ${busy === 'load' ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <p className="mb-3 text-[11px] text-muted-foreground">
        {total} methods across {HORIZONS.length} horizons. The catalog is a start, not a limit:
        literature extraction and <span className="font-mono">quant_register_method</span> add methods.
      </p>

      <div className="mb-3 grid gap-2 sm:grid-cols-2">
        <label className="text-[11px] text-muted-foreground">
          Objective
          <input
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
          />
        </label>
        <label className="text-[11px] text-muted-foreground">
          Horizon
          <select
            value={horizon}
            onChange={(event) => setHorizon(event.target.value)}
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
          >
            {HORIZONS.map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
        </label>
      </div>

      <div className="mb-3 grid gap-1 sm:grid-cols-2">
        {HORIZONS.map((h) => (
          <div key={h} className="flex items-center justify-between rounded-lg border border-white/5 px-2 py-1 text-[11px]">
            <span className="text-muted-foreground">{h}</span>
            <span className="font-mono">{(matrix[h] ?? []).length}</span>
          </div>
        ))}
      </div>

      <div className="mb-3 rounded-xl border border-white/5 p-2">
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search the literature"
            className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-foreground"
          />
          <button
            type="button"
            onClick={() => void search()}
            disabled={busy !== null}
            className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-3 py-1.5 text-[11px] disabled:opacity-50"
          >
            {busy === 'search' ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            Search
          </button>
        </div>
        {papers.length > 0 ? (
          <ul className="mt-2 max-h-40 space-y-1 overflow-auto">
            {papers.map((paper, index) => (
              <li key={String(paper.id ?? index)} className="flex items-start gap-2 text-[11px]">
                <button
                  type="button"
                  onClick={() => void extract(paper)}
                  disabled={busy !== null}
                  className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] disabled:opacity-50"
                >
                  Extract
                </button>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-foreground">{String(paper.title ?? '')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {String(paper.provider ?? '')}
                    {paper.isOpenAccess ? ' · open access' : ''}
                    {paper.year ? ` · ${String(paper.year)}` : ''}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {extracted ? (
          <p className="mt-2 text-[10px] text-muted-foreground">
            Extraction: {String(extracted.valid ? 'valid' : 'incomplete')} ·{' '}
            {String((extracted.draft as Record<string, unknown> | undefined)?.methodId ?? '')}
          </p>
        ) : null}
      </div>

      <div className="mb-3 max-h-40 overflow-auto rounded-xl border border-white/5 p-2">
        {allMethods.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">No methods loaded.</p>
        ) : allMethods.map((method) => (
          <label key={method.methodId} className="flex items-center gap-2 py-0.5 text-[11px]">
            <input
              type="checkbox"
              checked={selected.includes(method.methodId)}
              onChange={() => toggle(method.methodId)}
            />
            <span className="truncate">{method.name}</span>
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">
              {(method.horizons ?? []).join(' · ')}
            </span>
          </label>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void compare()}
          disabled={selected.length === 0 || busy !== null}
          className="inline-flex items-center gap-1 rounded-lg bg-primary/20 px-3 py-1.5 text-[11px] disabled:opacity-50"
        >
          {busy === 'compare' ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Compare
        </button>
        <button
          type="button"
          onClick={() => void visualize()}
          disabled={selected.length === 0 || busy !== null}
          className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-3 py-1.5 text-[11px] disabled:opacity-50"
        >
          {busy === 'visualize' ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Show data
        </button>
      </div>

      {comparison.length > 0 ? (
        <div className="mb-3 overflow-auto rounded-xl border border-white/5">
          <table className="w-full text-[11px]">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="px-2 py-1">Method</th>
                <th className="px-2 py-1">Fit</th>
                <th className="px-2 py-1">Why</th>
              </tr>
            </thead>
            <tbody>
              {comparison.map((row) => (
                <tr key={row.methodId} className="border-t border-white/5">
                  <td className="px-2 py-1">{row.name}</td>
                  <td className="px-2 py-1 font-mono">{row.score}/100</td>
                  <td className="px-2 py-1 text-muted-foreground">
                    {row.warnings[0] ?? row.factors.find((f) => f.points > 0)?.reason ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-2 py-1 text-[10px] text-muted-foreground">
            Fit is methodological suitability, not a probability of profit.
          </p>
        </div>
      ) : null}

      {blocks.length > 0 ? (
        <div className="grid gap-3">
          {blocks.map((block, index) => (
            <div key={block.id ?? index} className="rounded-xl border border-white/5 p-2">
              <ResponseChart block={block} height={220} focusable={false} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
