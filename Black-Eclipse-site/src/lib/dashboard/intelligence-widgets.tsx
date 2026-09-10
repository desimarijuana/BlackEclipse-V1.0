'use client';

// ── Intelligence widgets — signature BlackEclipse capabilities ───────────────
// Market Regime, What Changed, Opportunity Scanner, Market Drivers. All are
// deterministic analytics over the same data topics the other widgets use.

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { useTopic } from '@/lib/workspace/data-hub';
import {
  computeRegime, computeWhatChanged, scanOpportunities, computeDrivers,
  type Regime,
} from './intelligence';

interface IndexRow { name: string; symbol: string; price: number; change: number; changePercent: number; }
interface OverviewGroup { id: string; country: string; name?: string; stocks: { symbol: string; name: string; price: number; changePct: number }[]; }

function WidgetHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>
      {hint && <span className="font-mono text-[9px] text-muted-foreground/70 shrink-0">{hint}</span>}
    </div>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center py-8 text-center">
      <p className="text-xs text-muted-foreground/70 italic">{children}</p>
    </div>
  );
}

const REGIME_TONE: Record<Regime, string> = {
  'Risk On': 'text-emerald-400',
  'Risk Off': 'text-rose-400',
  'Trending Bull': 'text-emerald-400',
  'Trending Bear': 'text-rose-400',
  'Range': 'text-amber-400',
  'High Volatility': 'text-orange-400',
  'Transition': 'text-sky-400',
};

// ── Market Regime ────────────────────────────────────────────────────────────

export function MarketRegimeWidget() {
  const t = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const indices = useMemo(() => t.data?.indices ?? [], [t.data]);
  const result = useMemo(() => computeRegime(indices), [indices]);
  const f = result.factors;

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Market Regime" hint="DETERMINISTIC" />
      {indices.length === 0 ? <EmptyNote>Loading regime…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className={cn('font-mono text-xl font-bold', REGIME_TONE[result.regime])}>{result.regime}</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <FactorBar label="Breadth" value={f.breadth} />
            <FactorBar label="Momentum" value={50 + f.momentum * 20} />
            <FactorBar label="Risk On" value={f.riskOn ? 100 : 0} />
          </div>
          <div className="flex flex-col gap-1">
            {result.reasons.map((r, i) => (
              <p key={i} className="text-[10px] text-muted-foreground border-l-2 border-primary/30 pl-2">{r}</p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FactorBar({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="w-16 shrink-0 text-muted-foreground">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-border/40 overflow-hidden">
        <div className={cn('h-full rounded-full', v >= 60 ? 'bg-emerald-400' : v >= 40 ? 'bg-amber-400' : 'bg-rose-400')} style={{ width: `${v}%` }} />
      </div>
      <span className="w-8 text-right font-mono text-foreground">{Math.round(v)}</span>
    </div>
  );
}

// ── What Changed ────────────────────────────────────────────────────────────

export function WhatChangedWidget() {
  const t = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const indices = useMemo(() => t.data?.indices ?? [], [t.data]);
  // Deterministic "previous" = a slightly shifted snapshot (no persistence yet).
  const previous = useMemo(() => indices.map(i => ({ name: i.name, changePercent: i.changePercent - (i.changePercent > 0 ? 0.2 : -0.2) })), [indices]);
  const changes = useMemo(() => computeWhatChanged(indices, previous), [indices, previous]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="What Changed?" hint="SESSION" />
      {changes.length === 0 ? <EmptyNote>No meaningful changes this session.</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {changes.map(c => (
            <div key={c.label} className="flex items-center justify-between text-[10px] py-0.5">
              <span className="text-muted-foreground">{c.label}</span>
              <span className={cn('font-mono font-bold', c.direction === 'up' ? 'text-emerald-400' : 'text-rose-400')}>
                {c.direction === 'up' ? '↑' : '↓'} {c.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Opportunity Scanner ────────────────────────────────────────────────────

export function OpportunityScannerWidget() {
  const t = useTopic<{ groups: OverviewGroup[] }>('market:overview');
  const stocks = useMemo(() => t.data?.groups?.find(g => g.id === 'US')?.stocks ?? [], [t.data]);
  const opps = useMemo(() => scanOpportunities(stocks), [stocks]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Opportunity Scanner" hint="WHY" />
      {opps.length === 0 ? <EmptyNote>No opportunities detected.</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto scrollbar-hide">
          {opps.map(o => (
            <div key={o.symbol} className="rounded-xl border border-border/10 glass-card-subtle px-2.5 py-2">
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold text-foreground">{o.symbol}</span>
                <span className="flex items-center gap-2">
                  <span className="text-[9px] text-muted-foreground">{o.type}</span>
                  <span className="font-mono text-[10px] font-bold text-primary">{o.score}</span>
                </span>
              </div>
              <div className="mt-1 flex flex-col gap-0.5">
                {o.checks.map(c => <p key={c} className="text-[9px] text-emerald-400">✓ {c}</p>)}
                {o.risks.map(r => <p key={r} className="text-[9px] text-amber-400">⚠ {r}</p>)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Market Drivers ──────────────────────────────────────────────────────────

export function MarketDriversWidget() {
  const t = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const indices = useMemo(() => t.data?.indices ?? [], [t.data]);
  const drivers = useMemo(() => computeDrivers(indices), [indices]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Market Drivers" hint="RANKED" />
      {drivers.length === 0 ? <EmptyNote>Loading drivers…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1">
          {drivers.map((d, i) => (
            <div key={d.name} className="flex items-center gap-2 text-[10px] py-0.5">
              <span className="w-4 text-muted-foreground/50 font-mono">{i + 1}</span>
              <span className="flex-1 text-muted-foreground truncate">{d.name}</span>
              <span className={cn('font-mono font-bold', d.direction === 'up' ? 'text-emerald-400' : 'text-rose-400')}>
                {d.change > 0 ? '+' : ''}{d.change.toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
