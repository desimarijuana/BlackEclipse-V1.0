'use client';

import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import * as echarts from 'echarts';
import { Download, Loader2, Search, KeyRound, Sparkles, X } from 'lucide-react';
import type { EconSource } from '@/lib/economics/sources';
import { computeStats, sortByDate, type EconPoint } from '@/lib/economics/fetch';

interface ResearchResult {
  reportId: string;
  answer: string;
  verdict?: string;
  confidence?: number;
  agents: { name: string; status: string; toolCalls: number; toolErrors: number }[];
}

export interface PanelProps {
  source: EconSource;
}

const PAGE_SIZE = 25;

export function EconPanel({ source }: PanelProps) {
  const [params, setParams] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const c of source.controls) init[c.name] = c.defaultValue ?? '';
    return init;
  });
  const [rows, setRows] = useState<EconPoint[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keyRequired, setKeyRequired] = useState<string | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [research, setResearch] = useState<ResearchResult | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // Reset params when the source changes.
  useEffect(() => {
    const init: Record<string, string> = {};
    for (const c of source.controls) init[c.name] = c.defaultValue ?? '';
    setParams(init);
    setRows(null);
    setError(null);
    setKeyRequired(null);
    setResearch(null);
  }, [source]);

  const fetchSeries = useCallback(async (override?: Record<string, string>) => {
    const p = override ?? params;
    setLoading(true);
    setError(null);
    setKeyRequired(null);
    setResearch(null);
    try {
      const qs = new URLSearchParams({ source: source.id, ...Object.fromEntries(Object.entries(p).filter(([, v]) => v)) });
      const res = await fetch(`/api/economics?${qs.toString()}`);
      const data = await res.json();
      if (data.keyRequired) {
        setKeyRequired(data.keyEnv || 'UNKNOWN');
        setRows(null);
      } else if (data.error) {
        setError(data.error);
        setRows(null);
      } else {
        setRows(sortByDate(data.rows || []));
        setAsOf(data.asOf || null);
        setPage(1);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fetch failed');
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, [source, params]);

  useEffect(() => {
    void fetchSeries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source]);

  // ─── ECharts render ────────────────────────────────────────────────────
  const chartDeps = useMemo(() => {
    if (!rows) return null;
    const finite = rows.filter((r) => r.value !== null);
    const labelKey = detectLabelKey(finite);
    const grouped = new Map<string, EconPoint[]>();
    if (labelKey) {
      for (const r of finite) {
        const label = String(r[labelKey] ?? 'value');
        const arr = grouped.get(label) ?? [];
        arr.push(r);
        grouped.set(label, arr);
      }
    } else {
      grouped.set(source.label, finite);
    }
    const dates = [...new Set([...grouped.values()].flatMap((g) => g.map((r) => r.date)))].sort();
    const palette = ['#a78bfa', '#34d399', '#fbbf24', '#fb7185', '#38bdf8', '#f472b6'];
    const seriesNames = [...grouped.keys()].slice(0, 6);
    return {
      seriesNames,
      dates,
      grouped,
      palette,
      labelKey,
    };
  }, [rows, source.label]);

  useEffect(() => {
    if (!chartRef.current || !chartDeps) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }
    const { seriesNames, dates, grouped, palette } = chartDeps;
    const option: echarts.EChartsOption = {
      backgroundColor: 'transparent',
      grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(15,15,15,0.92)',
        borderColor: 'rgba(167,139,250,0.25)',
        textStyle: { color: '#e5e5e5', fontSize: 11, fontFamily: 'monospace' },
      },
      legend: seriesNames.length > 1
        ? { top: 0, textStyle: { color: '#a3a3a3', fontSize: 10 }, icon: 'roundRect', itemWidth: 12, itemHeight: 3 }
        : undefined,
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { color: '#737373', fontSize: 10, fontFamily: 'monospace' },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: '#737373', fontSize: 10, fontFamily: 'monospace' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      },
      series: seriesNames.map((name, i) => ({
        name,
        type: 'line' as const,
        showSymbol: false,
        data: (grouped.get(name) ?? []).map((r) => [r.date, r.value]),
        lineStyle: { width: 2, color: palette[i % palette.length] },
        itemStyle: { color: palette[i % palette.length] },
        areaStyle: seriesNames.length === 1
          ? { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
              { offset: 0, color: `${palette[i % palette.length]}30` },
              { offset: 1, color: `${palette[i % palette.length]}00` },
            ] } }
          : undefined,
      })),
    };
    chartInstance.current.setOption(option, true);
  }, [chartDeps]);

  useEffect(() => {
    const el = chartRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => chartInstance.current?.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  // ─── Stats ─────────────────────────────────────────────────────────────
  const stats = useMemo(() => (rows ? computeStats(rows) : null), [rows]);
  const isCrossSection = Boolean(stats && !stats.isTimeSeries);

  // ─── Table pagination ──────────────────────────────────────────────────
  const displayRows = useMemo(() => {
    if (!rows) return [];
    return sortByDate(rows).reverse(); // newest first in the table
  }, [rows]);
  const totalPages = Math.max(1, Math.ceil(displayRows.length / PAGE_SIZE));
  const pageRows = displayRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const valueKeys = useMemo(() => {
    if (!rows || rows.length === 0) return [];
    const sample = rows[0];
    return Object.keys(sample).filter((k) => !['date', 'value'].includes(k)).slice(0, 4);
  }, [rows]);

  // ─── CSV export with provenance header ─────────────────────────────────
  const exportCSV = () => {
    if (!rows || rows.length === 0) return;
    const ordered = sortByDate(rows);
    const cols = ['date', 'value', ...valueKeys];
    const provenance = `# source=${source.id} exported=${new Date().toISOString()} rows=${ordered.length}`;
    const lines = [provenance, cols.join(','), ...ordered.map((r) =>
      cols.map((c) => {
        const v = r[c];
        return typeof v === 'string' && v.includes(',') ? `"${v}"` : String(v ?? '');
      }).join(',')
    )];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${source.id}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ─── Real agent research ───────────────────────────────────────────────
  const runAnalysis = async () => {
    const label = params.indicator
      ? Object.values(params).filter(Boolean).join(' — ')
      : Object.values(params).filter(Boolean).join(', ');
    setResearchLoading(true);
    setResearch(null);
    try {
      const res = await fetch('/api/agent/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `Analyze this macro-economic data for decision-making: "${source.label}" (${label || 'full dataset'})${
            stats?.latest !== null && stats?.latest !== undefined
              ? `. Latest value ${stats.latest}${stats.asOf ? ` as of ${stats.asOf}` : ''}`
              : ''
          }. What does this series say about the macro outlook, and what should investors watch next?`,
          market: 'US',
        }),
      });
      const data = await res.json();
      if (data.success) {
        setResearch({ reportId: data.reportId, answer: data.answer, verdict: data.verdict, confidence: data.confidence, agents: data.agents || [] });
      } else {
        setError(data.error || 'Research failed');
      }
    } catch {
      setError('Failed to reach the research engine');
    } finally {
      setResearchLoading(false);
    }
  };

  const setParam = (name: string, value: string) => {
    const next = { ...params, [name]: value };
    setParams(next);
    void fetchSeries(next);
  };

  // ─── Render states ─────────────────────────────────────────────────────
  return (
    <div className="w-full rounded-2xl border border-border/10 bg-[#0f0f0f]/60 backdrop-blur-xl p-4 flex flex-col gap-4 animate-fade-in-up">
      {/* Toolbar — declarative controls + FETCH/CSV */}
      <div className="flex items-center gap-2 flex-wrap">
        {source.controls.map((control) => (
          <label key={control.name} className="flex flex-col gap-1 min-w-[160px]">
            <span className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground/70">{control.label}</span>
            {control.type === 'select' ? (
              <select
                value={params[control.name] ?? ''}
                onChange={(e) => setParam(control.name, e.target.value)}
                className="h-9 appearance-none rounded-lg bg-accent/30 border border-border/30 pl-3 pr-8 text-[12px] font-mono text-foreground cursor-pointer focus:outline-none focus:border-primary/60 transition-colors"
              >
                {(control.options ?? []).map((o) => (
                  <option key={o.value} value={o.value} className="bg-background text-foreground">{o.label}</option>
                ))}
              </select>
            ) : (
              <input
                type={control.type === 'date' ? 'date' : control.type === 'range' ? 'number' : 'text'}
                value={params[control.name] ?? ''}
                onChange={(e) => setParams((prev) => ({ ...prev, [control.name]: e.target.value }))}
                className="h-9 rounded-lg bg-accent/30 border border-border/30 px-3 text-[12px] font-mono text-foreground focus:outline-none focus:border-primary/60 transition-colors"
              />
            )}
          </label>
        ))}
        <span className="flex-1" />
        <button
          onClick={() => void fetchSeries()}
          disabled={loading}
          className="h-9 px-4 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 text-[12px] font-semibold inline-flex items-center gap-1.5 cursor-pointer transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />} Fetch
        </button>
        <button
          onClick={exportCSV}
          disabled={!rows || rows.length === 0}
          className="h-9 px-3 rounded-lg bg-accent/40 hover:bg-accent/70 border border-border/40 text-muted-foreground hover:text-foreground text-[12px] font-semibold inline-flex items-center gap-1.5 cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Download size={12} /> CSV
        </button>
      </div>

      {/* Key-gated setup prompt */}
      {keyRequired && (
        <div className="p-4 rounded-xl bg-amber-400/5 border border-amber-400/30 flex items-start gap-3">
          <KeyRound size={16} className="text-amber-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-[13px] font-semibold text-amber-400">API key required</p>
            <p className="text-[12px] text-muted-foreground mt-1">
              Set <span className="font-mono text-amber-400">{keyRequired}</span> in Settings / .env to enable this source.
            </p>
          </div>
        </div>
      )}

      {error && !keyRequired && (
        <div className="p-4 rounded-xl bg-rose-500/5 border border-rose-500/30">
          <p className="text-[12px] font-semibold text-rose-400 font-mono">{error}</p>
          <button onClick={() => void fetchSeries()} className="mt-2 px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/25 text-[11px] font-semibold cursor-pointer transition-colors">
            Retry
          </button>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !rows && (
        <div className="flex flex-col gap-2 py-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-8 rounded-lg bg-accent/20 animate-pulse" />)}
        </div>
      )}

      {/* Stat cards row — hidden for cross-sections */}
      {stats && !isCrossSection && stats.points > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {([
            ['LATEST', stats.latest != null ? fmt(stats.latest) : '—', stats.asOf ? `as of ${stats.asOf}` : ''],
            ['CHANGE', stats.change != null ? `${fmtPct(stats.change)}` : '—', 'vs previous'],
            ['MIN', stats.min != null ? fmt(stats.min) : '—', ''],
            ['MAX', stats.max != null ? fmt(stats.max) : '—', ''],
            ['AVG', stats.avg != null ? fmt(stats.avg) : '—', ''],
            ['POINTS', String(stats.points), 'observations'],
          ] as [string, string, string][]).map(([label, value, sub]) => (
            <div key={label} className="p-2.5 rounded-xl bg-accent/20 border border-border/20">
              <p className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground/70">{label}</p>
              <p className={`text-[15px] font-bold font-mono mt-0.5 ${label === 'CHANGE' ? (stats.change != null && stats.change >= 0 ? 'text-emerald-400' : 'text-rose-400') : 'text-foreground'}`}>
                {value}
              </p>
              {sub && <p className="text-[9px] text-muted-foreground/60 mt-0.5">{sub}</p>}
            </div>
          ))}
        </div>
      )}

      {/* Vintage line */}
      {asOf && (
        <p className="text-[10px] font-mono text-muted-foreground/70 px-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 align-middle" />
          {source.label} · as of {asOf} · {rows?.length ?? 0} observations
        </p>
      )}

      {/* Chart */}
      {chartDeps && chartDeps.dates.length > 1 && (
        <div ref={chartRef} className="w-full h-72 rounded-xl bg-accent/10 border border-border/20" />
      )}

      {/* Cross-section note */}
      {isCrossSection && (
        <p className="text-[10px] font-mono text-muted-foreground/60 px-1">
          Cross-section result — one row per unit, no time dimension. Stats and chart hidden.
        </p>
      )}

      {/* AI analysis */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => void runAnalysis()}
          disabled={researchLoading || !rows || rows.length === 0}
          className="h-9 px-4 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 text-[12px] font-semibold inline-flex items-center gap-1.5 cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {researchLoading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          {researchLoading ? 'Analyzing…' : 'Analyze with AI'}
        </button>
        {research && (
          <button onClick={() => setResearch(null)} className="h-9 px-3 rounded-lg border border-border/40 text-muted-foreground hover:text-foreground text-[11px] inline-flex items-center gap-1 cursor-pointer">
            <X size={11} /> Close
          </button>
        )}
      </div>
      {research && (
        <div className="p-4 rounded-xl bg-primary/[0.04] border border-primary/20 animate-fade-in-up">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Sparkles size={13} className="text-primary" />
            <span className="text-[11px] font-bold text-primary uppercase tracking-wider">AI Research</span>
            {research.verdict && (
              <span className="text-[10px] font-bold font-mono uppercase px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                {research.verdict}
              </span>
            )}
            {typeof research.confidence === 'number' && (
              <span className="text-[10px] font-mono text-muted-foreground">confidence {Math.round(research.confidence * 100)}%</span>
            )}
          </div>
          <p className="text-[12px] text-foreground/90 leading-relaxed whitespace-pre-wrap">{research.answer}</p>
          {research.agents.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-border/20">
              {research.agents.map((a) => (
                <span key={a.name} className="text-[9px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-accent/40 border border-border/30 text-muted-foreground">
                  {a.name} · {a.status} · {a.toolCalls} tools
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Table */}
      {rows && rows.length > 0 && (
        <div className="rounded-xl border border-border/20 overflow-hidden">
          <div className="overflow-x-auto max-h-80 overflow-y-auto">
            <table className="w-full text-[12px] font-mono">
              <thead className="sticky top-0 bg-[#0f0f0f]/95 backdrop-blur border-b border-border/20">
                <tr>
                  <th className="text-left px-3 py-2 text-[9px] uppercase tracking-wider text-muted-foreground font-bold">Date</th>
                  <th className="text-right px-3 py-2 text-[9px] uppercase tracking-wider text-muted-foreground font-bold">Value</th>
                  {valueKeys.slice(0, 2).map((k) => (
                    <th key={k} className="text-right px-3 py-2 text-[9px] uppercase tracking-wider text-muted-foreground font-bold">{k}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r, i) => (
                  <tr key={`${r.date}-${i}`} className="border-b border-border/10 last:border-0 hover:bg-accent/20 transition-colors">
                    <td className="px-3 py-1.5 text-muted-foreground" style={{ borderLeft: `3px solid ${source.color}` }}>{r.date}</td>
                    <td className="px-3 py-1.5 text-right font-bold text-foreground">{r.value !== null ? fmt(r.value) : <span className="text-muted-foreground/40">—</span>}</td>
                    {valueKeys.slice(0, 2).map((k) => (
                      <td key={k} className="px-3 py-1.5 text-right text-muted-foreground/80 truncate max-w-[140px]">{String(r[k] ?? '')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-border/20 text-[11px] font-mono text-muted-foreground">
              <span>page {page} of {totalPages} · {rows.length} rows</span>
              <div className="flex gap-1.5">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-2.5 py-1 rounded-lg bg-accent/40 hover:bg-accent/70 border border-border/40 disabled:opacity-40 cursor-pointer">Prev</button>
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="px-2.5 py-1 rounded-lg bg-accent/40 hover:bg-accent/70 border border-border/40 disabled:opacity-40 cursor-pointer">Next</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {rows && rows.length === 0 && !loading && (
        <div className="py-8 text-center text-[12px] font-mono text-muted-foreground border border-dashed border-border/25 rounded-xl">
          No observations returned for this query. Try different parameters.
        </div>
      )}
    </div>
  );
}

// Detect a categorical label column (e.g. country / indicator) that indicates
// multiple series in the result — used for multi-series chart overlay.
function detectLabelKey(rows: EconPoint[]): string | null {
  if (rows.length < 4) return null;
  for (const key of ['country', 'countryName', 'country_name', 'geo', 'ref_area', 'indicator', 'seriesName', 'location', 'name']) {
    const vals = new Set(rows.map((r) => String(r[key] ?? '')));
    if (vals.size >= 2 && vals.size <= 20) return key;
  }
  return null;
}

function fmt(v: number): string {
  if (!Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(Number(v.toFixed(4)));
}

function fmtPct(v: number): string {
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;
}