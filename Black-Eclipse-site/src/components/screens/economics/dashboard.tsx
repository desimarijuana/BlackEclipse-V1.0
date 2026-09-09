'use client';

import React, { useState, useEffect } from 'react';
import { Loader2, TrendingUp, TrendingDown, Activity, Gauge } from 'lucide-react';

// ─── Decision widgets for the Economics page ─────────────────────────────
// Each widget fetches a small set of FRED series and renders a decision
// signal (real rate, yield-curve health, regime, rate path, dollar gauge).

interface Point { date: string; value: number | null; }

async function fetchSeries(source: string, series: string): Promise<Point[]> {
  const res = await fetch(`/api/economics?source=${source}&series=${series}`);
  const d = await res.json();
  return (d.rows || []).map((r: { date: string; value: number | null }) => ({ date: r.date, value: r.value }));
}

function last(points: Point[]): number | null {
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i].value !== null) return points[i].value;
  }
  return null;
}

function fmt(v: number | null, digits = 2): string {
  if (v === null || !Number.isFinite(v)) return '—';
  return v.toFixed(digits);
}

// ─── Real-rate card: policy rate − CPI ───────────────────────────────────
function RealRateCard() {
  const [rate, setRate] = useState<number | null>(null);
  const [cpi, setCpi] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const [r, c] = await Promise.all([
          fetchSeries('real-rate', 'DFF'),
          fetchSeries('real-rate', 'CPIAUCSL'),
        ]);
        setRate(last(r));
        setCpi(last(c));
      } finally { setLoading(false); }
    })();
  }, []);

  const real = rate !== null && cpi !== null ? rate - cpi : null;
  const positive = real !== null && real > 0;

  return (
    <WidgetCard title="Real Rate" icon={<Activity size={14} />} loading={loading}
      desc="Policy rate − CPI · the real cost of money">
      <div className="flex items-end justify-between">
        <div>
          <div className={`text-2xl font-bold font-mono ${positive ? 'text-primary' : 'text-rose-400'}`}>
            {fmt(real)}%
          </div>
          <div className="text-[10px] font-mono text-muted-foreground mt-0.5">
            {positive ? 'Restrictive' : 'Accommodative'}
          </div>
        </div>
        <div className="text-right font-mono text-[10px] text-muted-foreground">
          <div>Policy {fmt(rate)}%</div>
          <div>CPI {fmt(cpi)}%</div>
        </div>
      </div>
    </WidgetCard>
  );
}

// ─── Yield-curve health: 2s10s spread ────────────────────────────────────
function YieldCurveCard() {
  const [s2, setS2] = useState<number | null>(null);
  const [s10, setS10] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const [a, b] = await Promise.all([
          fetchSeries('yield-curve', 'DGS2'),
          fetchSeries('yield-curve', 'DGS10'),
        ]);
        setS2(last(a));
        setS10(last(b));
      } finally { setLoading(false); }
    })();
  }, []);

  const spread = s2 !== null && s10 !== null ? s10 - s2 : null;
  const label = spread === null ? '—' : spread < 0 ? 'Inverted' : spread < 0.5 ? 'Flat' : 'Steep';
  const color = spread === null ? '' : spread < 0 ? 'text-rose-400' : spread < 0.5 ? 'text-amber-400' : 'text-primary';

  return (
    <WidgetCard title="Yield Curve" icon={<TrendingUp size={14} />} loading={loading}
      desc="2s10s spread · recession signal">
      <div className="flex items-end justify-between">
        <div>
          <div className={`text-2xl font-bold font-mono ${color}`}>{fmt(spread)}%</div>
          <div className="text-[10px] font-mono text-muted-foreground mt-0.5">{label}</div>
        </div>
        <div className="text-right font-mono text-[10px] text-muted-foreground">
          <div>2Y {fmt(s2)}%</div>
          <div>10Y {fmt(s10)}%</div>
        </div>
      </div>
    </WidgetCard>
  );
}

// ─── Growth/inflation regime quadrant ────────────────────────────────────
function RegimeCard() {
  const [gdp, setGdp] = useState<number | null>(null);
  const [cpi, setCpi] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const [g, c] = await Promise.all([
          fetchSeries('fincept-macro', 'GDPC1'),
          fetchSeries('fincept-macro', 'CPIAUCSL'),
        ]);
        setGdp(last(g));
        setCpi(last(c));
      } finally { setLoading(false); }
    })();
  }, []);

  // Regime from growth vs inflation direction (simplified).
  const regime = gdp === null || cpi === null ? '—' : cpi > 3 ? 'Stagflation risk' : gdp > 2 ? 'Goldilocks' : 'Slowdown';
  const color = regime === 'Goldilocks' ? 'text-primary' : regime === 'Stagflation risk' ? 'text-rose-400' : 'text-amber-400';

  return (
    <WidgetCard title="Macro Regime" icon={<Gauge size={14} />} loading={loading}
      desc="Growth vs inflation regime">
      <div className="flex items-end justify-between">
        <div>
          <div className={`text-xl font-bold ${color}`}>{regime}</div>
          <div className="text-[10px] font-mono text-muted-foreground mt-0.5">GDP {fmt(gdp, 1)}% · CPI {fmt(cpi, 1)}%</div>
        </div>
      </div>
    </WidgetCard>
  );
}

// ─── Rate-hike/cut probability gauge ────────────────────────────────────
function RatePathCard() {
  const [rate, setRate] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetchSeries('real-rate', 'DFF');
        setRate(last(r));
      } finally { setLoading(false); }
    })();
  }, []);

  // Simplified stance: high rate + falling inflation → easing bias.
  const stance = rate === null ? '—' : rate > 4 ? 'Hawkish' : rate > 2 ? 'Neutral' : 'Dovish';
  const color = stance === 'Hawkish' ? 'text-rose-400' : stance === 'Dovish' ? 'text-primary' : 'text-amber-400';

  return (
    <WidgetCard title="Policy Stance" icon={<TrendingDown size={14} />} loading={loading}
      desc="Fed funds level · easing/hiking bias">
      <div className="flex items-end justify-between">
        <div>
          <div className={`text-xl font-bold ${color}`}>{stance}</div>
          <div className="text-[10px] font-mono text-muted-foreground mt-0.5">Fed funds {fmt(rate)}%</div>
        </div>
      </div>
    </WidgetCard>
  );
}

// ─── Dollar strength gauge ──────────────────────────────────────────────
function DollarCard() {
  const [dxy, setDxy] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const d = await fetchSeries('dollar', 'DTWEXBGS');
        setDxy(last(d));
      } finally { setLoading(false); }
    })();
  }, []);

  const strength = dxy === null ? '—' : dxy > 120 ? 'Strong' : dxy > 100 ? 'Firm' : 'Weak';
  const color = strength === 'Weak' ? 'text-rose-400' : strength === 'Strong' ? 'text-primary' : 'text-amber-400';

  return (
    <WidgetCard title="Dollar Gauge" icon={<TrendingUp size={14} />} loading={loading}
      desc="Broad dollar index · EM & commodity driver">
      <div className="flex items-end justify-between">
        <div>
          <div className={`text-xl font-bold ${color}`}>{strength}</div>
          <div className="text-[10px] font-mono text-muted-foreground mt-0.5">DXY {fmt(dxy, 1)}</div>
        </div>
      </div>
    </WidgetCard>
  );
}

// ─── Shared card shell ───────────────────────────────────────────────────
function WidgetCard({ title, icon, desc, loading, children }: {
  title: string; icon: React.ReactNode; desc: string; loading: boolean; children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl bg-[#0f0f0f]/60 border border-border/10 p-4 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-primary">{icon}</span>
        <span className="text-[12px] font-semibold text-foreground">{title}</span>
        {loading && <Loader2 size={11} className="animate-spin text-muted-foreground ml-auto" />}
      </div>
      <p className="text-[10px] text-muted-foreground">{desc}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}

export function DecisionDashboard() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
      <RealRateCard />
      <YieldCurveCard />
      <RegimeCard />
      <RatePathCard />
      <DollarCard />
    </div>
  );
}
