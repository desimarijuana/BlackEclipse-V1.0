'use client';

import React, { useState, useEffect } from 'react';
import { RefreshCw, Loader2, Sparkles, AlertTriangle } from 'lucide-react';

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

// FRED series id shown as provenance on each card.
const FRED_ID: Record<string, string> = {
  'fed-funds': 'DFEDTARU',
  'boe-rate': 'BOERUKM',
  'ecb-rate': 'ECBDFR',
  'boj-rate': 'IRSTCI01JPM156N',
  'rba-rate': 'IRSTCI01AUM156N',
  'rbnz-rate': 'IRSTCI01NZM156N',
  'boc-rate': 'IRSTCI01CAM156N',
  'snb-rate': 'IRSTCI01CHM156N',
  'rbi-rate': 'IRSTCI01INM156N',
  'sbp-rate': 'IRSTCI01PKM156N',
  'pboc-rate': 'IRSTCI01CNM156N',
  'us-cpi': 'CPIAUCSL',
  'us-gdp': 'GDPC1',
  'us-nfp': 'PAYEMS',
  'us-unemp': 'UNRATE',
  'us-10y': 'DGS10',
  'in-cpi': 'CPALTT01INM659N',
  'in-gdp': 'NGDPRSAXDCCINQ',
  'in-unemp': 'LRUN64TTINQ156S',
  'pk-cpi': 'CPALTT01PKM659N',
  'pk-gdp': 'NGDPRSAXDCPKQ',
  'pk-unemp': 'LRUN64TTPKQ156S',
  'cn-cpi': 'CPALTT01CNM659N',
  'cn-gdp': 'NGDPRSAXDCCNQ',
  'gb-cpi': 'CPALTT01GBM659N',
  'gb-unemp': 'LRUN64TTGBQ156S',
  'eu-cpi': 'CP0000EZ19M086NEST',
  'eu-unemp': 'LRHUTTTTEZM156S',
  'jp-cpi': 'CPALTT01JPM659N',
  'jp-unemp': 'LRUN64TTJPM156S',
  'ca-cpi': 'CPALTT01CAM659N',
  'ca-unemp': 'LRUN64TTCAQ156S',
};

const FLAG: Record<string, string> = {
  'fed-funds': 'FED · US',
  'boe-rate': 'BOE · UK',
  'ecb-rate': 'ECB · EU',
  'boj-rate': 'BOJ · JP',
  'rba-rate': 'RBA · AU',
  'rbnz-rate': 'RBNZ · NZ',
  'boc-rate': 'BOC · CA',
  'snb-rate': 'SNB · CH',
  'rbi-rate': 'RBI · IN',
  'sbp-rate': 'SBP · PK',
  'pboc-rate': 'PBOC · CN',
  'us-cpi': 'US · CPI',
  'us-gdp': 'US · GDP',
  'us-nfp': 'US · JOBS',
  'us-unemp': 'US · LABOUR',
  'us-10y': 'US · RATES',
  'in-cpi': 'IN · CPI',
  'in-gdp': 'IN · GDP',
  'in-unemp': 'IN · LABOUR',
  'pk-cpi': 'PK · CPI',
  'pk-gdp': 'PK · GDP',
  'pk-unemp': 'PK · LABOUR',
  'cn-cpi': 'CN · CPI',
  'cn-gdp': 'CN · GDP',
  'gb-cpi': 'UK · CPI',
  'gb-unemp': 'UK · LABOUR',
  'eu-cpi': 'EU · HICP',
  'eu-unemp': 'EU · LABOUR',
  'jp-cpi': 'JP · CPI',
  'jp-unemp': 'JP · LABOUR',
  'ca-cpi': 'CA · CPI',
  'ca-unemp': 'CA · LABOUR',
};

// Order in which macro-print regions render on the Snapshot.
const REGION_ORDER = ['North America', 'Asia-Pacific', 'Europe'];

export function SnapshotView() {
  const [data, setData] = useState<SnapshotData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [research, setResearch] = useState<ResearchResult | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);

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

  const rates = data?.metrics.filter((m) => m.kind === 'rate') ?? [];
  const prints = data?.metrics.filter((m) => m.kind !== 'rate') ?? [];
  const builtAt = data?.builtAt ? new Date(data.builtAt) : null;

  return (
    <div className="flex flex-col gap-6">
      {/* Vintage + controls */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-[10px] font-mono text-muted-foreground/70">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary mr-1.5 align-middle" />
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

      {/* Central-bank policy rates */}
      <div>
        <p className="text-[12px] font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-2.5">
          Central-bank policy rates · FRED
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2.5">
          {rates.map((m) => <SnapCard key={m.id} m={m} />)}
        </div>
      </div>

      {/* Global macro prints, grouped by region */}
      {REGION_ORDER.map((region) => {
        const regionPrints = prints.filter((m) => m.region === region);
        if (regionPrints.length === 0) return null;
        return (
          <div key={region}>
            <p className="text-[12px] font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-2.5">
              {region} · FRED
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2.5">
              {regionPrints.map((m) => <SnapCard key={m.id} m={m} />)}
            </div>
          </div>
        );
      })}

      {/* Data provenance */}
      <div className="rounded-xl glass-card border border-border/10 p-5">
        <p className="text-[12px] font-semibold uppercase tracking-[0.05em] text-muted-foreground mb-2">
          Data provenance
        </p>
        <p className="text-[13px] text-muted-foreground leading-relaxed">
          Every metric above is pulled from the FRED public CSV feed and shows its value plus the{' '}
          <span className="font-mono text-foreground">“as of”</span> vintage. No number on this screen is invented — if a
          series is unavailable, the card is omitted rather than filled with a placeholder.
        </p>
      </div>
    </div>
  );
}

function SnapCard({ m }: { m: SnapshotMetric }) {
  const isNfp = m.id === 'us-nfp';
  const displayValue = isNfp && m.value !== null ? (m.value / 1000).toFixed(1) : m.value !== null ? Number(m.value.toFixed(3)) : null;
  const displayUnit = isNfp ? 'M' : m.unit;
  return (
    <div className="rounded-xl glass-card border border-border/10 p-3.5 flex flex-col">
      <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
        {FLAG[m.id] ?? m.country}
      </div>
      <div className="text-[12px] text-muted-foreground mt-0.5">{m.label}</div>
      {m.value !== null ? (
        <>
          <div className="font-mono text-[22px] font-semibold mt-1.5 text-foreground">
            {displayValue}
            {displayUnit && <span className="text-[12px] text-muted-foreground ml-0.5">{displayUnit}</span>}
          </div>
          <div className="font-mono text-[10px] text-muted-foreground mt-1">as of {m.asOf}</div>
          <div className="font-mono text-[10px] text-primary mt-0.5">FRED · {FRED_ID[m.id] ?? m.id}</div>
        </>
      ) : (
        <div className="text-[11px] text-muted-foreground/60 font-mono flex items-center gap-1 mt-1.5">
          <AlertTriangle size={10} /> unavailable
        </div>
      )}
    </div>
  );
}
