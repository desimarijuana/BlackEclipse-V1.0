'use client';

import React, { useState, useEffect, useRef } from 'react';
import { RefreshCw, Loader2, Sparkles } from 'lucide-react';
import * as echarts from 'echarts';

interface SnapshotMetric {
  id: string;
  label: string;
  region: string;
  kind: 'rate' | 'print' | 'yield';
  value: number | null;
  asOf: string | null;
  unit: string;
  country: string;
}

interface SnapshotData {
  metrics: SnapshotMetric[];
  builtAt: string;
}

interface ResearchResult {
  answer: string;
  verdict?: string;
  confidence?: number;
}

const REGION_ORDER = ['North America', 'Europe', 'Asia-Pacific'];

const KIND_STYLE: Record<SnapshotMetric['kind'], { border: string; text: string; badge: string; badgeLabel: string }> = {
  rate: { border: 'border-indigo-400/25', text: 'text-indigo-300', badge: 'bg-indigo-400/10 text-indigo-300 border-indigo-400/30', badgeLabel: 'POLICY RATE' },
  print: { border: 'border-emerald-400/25', text: 'text-emerald-300', badge: 'bg-emerald-400/10 text-emerald-300 border-emerald-400/30', badgeLabel: 'MACRO PRINT' },
  yield: { border: 'border-amber-400/25', text: 'text-amber-300', badge: 'bg-amber-400/10 text-amber-300 border-amber-400/30', badgeLabel: 'YIELD' },
};

export function SnapshotView() {
  const [data, setData] = useState<SnapshotData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [research, setResearch] = useState<ResearchResult | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  const load = async () => {
    setError(null);
    try {
      const res = await fetch('/api/economics/snapshot');
      const d = await res.json();
      setData(d);
    } catch {
      setError('Failed to load the global macro snapshot');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const refresh = async () => {
    setRefreshing(true);
    try { await load(); } finally { setRefreshing(false); }
  };

  const runAnalysis = async () => {
    const metrics = data?.metrics.filter((m) => m.value !== null) ?? [];
    if (metrics.length === 0) return;
    setResearchLoading(true);
    setResearch(null);
    try {
      const summary = metrics.map((m) => `${m.label}: ${Number(m.value!.toFixed(3))}${m.unit} (as of ${m.asOf})`).join('; ');
      const res = await fetch('/api/agent/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `Analyze the current global macro environment from these central-bank rates and key prints: ${summary}. What is the policy stance mix across regions, and what should investors watch next?`,
          market: 'US',
        }),
      });
      const d = await res.json();
      if (d.success) setResearch({ answer: d.answer, verdict: d.verdict, confidence: d.confidence });
      else setError(d.error || 'Research failed');
    } catch {
      setError('Failed to reach the research engine');
    } finally {
      setResearchLoading(false);
    }
  };

  // Rate spread mini-chart: Fed / ECB / BoE / BoJ policy rates side by side.
  useEffect(() => {
    if (!data || !chartRef.current) return;
    if (!chartInstance.current) chartInstance.current = echarts.init(chartRef.current);
    const rateMetrics = data.metrics.filter((m) => m.kind === 'rate' && m.value !== null);
    chartInstance.current.setOption({
      backgroundColor: 'transparent',
      grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(15,15,15,0.92)', textStyle: { color: '#e5e5e5', fontSize: 11, fontFamily: 'monospace' } },
      xAxis: { type: 'category', data: rateMetrics.map((m) => m.country), axisLabel: { color: '#737373', fontSize: 10, fontFamily: 'monospace' } },
      yAxis: { type: 'value', axisLabel: { color: '#737373', fontSize: 10, fontFamily: 'monospace' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
      series: [{
        type: 'bar', barWidth: 20,
        data: rateMetrics.map((m) => m.value),
        itemStyle: { color: (p: { dataIndex: number }) => (rateMetrics[p.dataIndex].value ?? 0) >= 0 ? '#a78bfa' : '#fb7185', borderRadius: 4 },
        label: { show: true, position: 'top', color: '#a3a3a3', fontSize: 10, fontFamily: 'monospace', formatter: (p: { value: number }) => `${Number(p.value.toFixed(2))}%` },
      }],
    }, true);
  }, [data]);

  useEffect(() => () => { chartInstance.current?.dispose(); chartInstance.current = null; }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground text-xs font-mono">
        <Loader2 size={14} className="animate-spin" /> Loading global macro snapshot…
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-4 rounded-xl bg-rose-500/5 border border-rose-500/30 text-[12px] text-rose-400 font-mono">{error}</div>
    );
  }

  const regions = REGION_ORDER.filter((r) => data?.metrics.some((m) => m.region === r));
  const builtAt = data?.builtAt ? new Date(data.builtAt) : null;

  return (
    <div className="flex flex-col gap-4">
      {/* Vintage + controls */}
      <div className="flex items-center justify-between px-1 flex-wrap gap-2">
        <p className="text-[10px] font-mono text-muted-foreground/70">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 align-middle" />
          {builtAt ? `Global Macro Snapshot · built ${builtAt.toUTCString()}` : 'Global Macro Snapshot'}
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => void runAnalysis()}
            disabled={researchLoading}
            className="h-8 px-3 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 text-[11px] font-bold inline-flex items-center gap-1.5 cursor-pointer transition-colors disabled:opacity-40"
          >
            {researchLoading ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} Analyze macro regime
          </button>
          <button
            onClick={() => void refresh()}
            disabled={refreshing}
            className="h-8 px-3 rounded-lg bg-accent/40 hover:bg-accent/70 border border-border/40 text-muted-foreground hover:text-foreground text-[11px] font-bold inline-flex items-center gap-1.5 cursor-pointer transition-colors disabled:opacity-50"
          >
            <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Policy-rate spread chart */}
      <div ref={chartRef} className="w-full h-56 rounded-xl bg-accent/10 border border-border/20" />

      {/* AI analysis panel */}
      {research && (
        <div className="p-4 rounded-xl bg-primary/[0.04] border border-primary/20 animate-fade-in-up">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Sparkles size={13} className="text-primary" />
            <span className="text-[11px] font-bold text-primary uppercase tracking-wider">Macro Regime Analysis</span>
            {research.verdict && (
              <span className="text-[10px] font-bold font-mono uppercase px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">{research.verdict}</span>
            )}
            {typeof research.confidence === 'number' && (
              <span className="text-[10px] font-mono text-muted-foreground">confidence {Math.round(research.confidence * 100)}%</span>
            )}
          </div>
          <p className="text-[12px] text-foreground/90 leading-relaxed whitespace-pre-wrap">{research.answer}</p>
        </div>
      )}

      {/* Cards grouped by region */}
      {regions.map((region) => (
        <div key={region}>
          <p className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground/70 mb-2 px-1">{region}</p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {data!.metrics.filter((m) => m.region === region).map((m) => {
              const style = KIND_STYLE[m.kind];
              return (
                <div key={m.id} className={`p-3.5 rounded-xl bg-accent/20 border ${style.border} flex flex-col gap-1.5`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${style.badge}`}>{style.badgeLabel}</span>
                    <span className="text-[9px] font-mono font-bold text-muted-foreground">{m.country}</span>
                  </div>
                  <p className="text-[12px] font-semibold text-foreground">{m.label}</p>
                  {m.value !== null ? (
                    <>
                      <p className={`text-xl font-bold font-mono ${style.text}`}>
                        {Number(m.value.toFixed(3))}<span className="text-[11px] text-muted-foreground ml-1">{m.unit}</span>
                      </p>
                      <p className="text-[9px] font-mono text-muted-foreground/60">as of {m.asOf}</p>
                    </>
                  ) : (
                    <p className="text-[11px] text-muted-foreground/60 font-mono flex items-center gap-1">
                      <AlertTriangle size={10} /> unavailable
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}