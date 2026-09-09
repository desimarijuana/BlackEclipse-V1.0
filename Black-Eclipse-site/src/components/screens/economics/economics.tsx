'use client';

import React, { useState } from 'react';
import { Globe } from 'lucide-react';
import { ECON_SOURCES } from '@/lib/economics/sources';
import { EconPanel } from './panel';
import { SnapshotView } from './snapshot';
import { CalendarView } from './calendar';

// Group the source registry into the reference's taxonomy. Each group renders
// as its own section with a tab bar to pick which source to view.
const SOURCE_GROUPS: { label: string; ids: string[] }[] = [
  { label: 'Multilateral', ids: ['worldbank', 'imf', 'fred', 'fred-analytics', 'oecd', 'ecb', 'eurostat'] },
  { label: 'US agencies', ids: ['bls', 'census', 'fiscaldata', 'bea', 'nber', 'federalreserve'] },
  { label: 'Market / commercial', ids: ['trading-economics', 'economic-calendar', 'econdb', 'bis', 'cftc', 'eia', 'wto'] },
  { label: 'National stats', ids: ['ons-uk', 'bcb', 'akshare-china', 'statcan'] },
  { label: 'International / thematic', ids: ['central-banks', 'ilo', 'un-comtrade', 'wb-health', 'adb', 'unesco', 'owid', 'fincept-macro'] },
  { label: 'Decision indicators', ids: ['real-rate', 'yield-curve', 'breakeven', 'credit-spread', 'money-supply', 'leading-indicators', 'pmi', 'consumer-confidence', 'housing', 'fed-balance-sheet', 'dollar', 'liquidity'] },
];

export function EconomicsScreen() {
  return (
    <div className="w-full max-w-7xl mx-auto px-4 md:px-8 py-8 h-full overflow-y-auto pb-20">
      <div className="animate-fade-in-up flex flex-col gap-10">
        {/* ── Hero ─────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
              <Globe className="text-primary" size={26} />
            </div>
            <h1 className="font-serif text-3xl md:text-4xl font-semibold tracking-tight text-foreground">
              Economics
            </h1>
          </div>
          <p className="text-[15px] text-muted-foreground mt-3 max-w-[60ch] leading-relaxed">
            Snapshot, explore and calendar the global macro picture. Every value carries its source and vintage — nothing fabricated.
          </p>
        </section>

        {/* ── SNAPSHOT ──────────────────────────────────────────── */}
        <section className="border-t border-border/10 pt-8">
          <SectionHead
            title="Global macro · live vintages"
            desc="Central-bank rates & key US prints, each with its “as of” vintage — pulled from the FRED public CSV feed. Nothing fabricated."
          />
          <SnapshotView />
        </section>

        {/* ── CALENDAR ─────────────────────────────────────────── */}
        <section className="border-t border-border/10 pt-8">
          <SectionHead
            title="Economic calendar"
            desc="Schedule only · no fabricated numbers. Forecasts appear only when a real consensus exists."
          />
          <CalendarView />
        </section>

        {/* ── EXPLORER ─────────────────────────────────────────── */}
        <section className="border-t border-border/10 pt-8">
          <SectionHead
            title="Time-series explorer"
            desc="Each category below has its own tab bar — click a source to chart its history."
          />

          <div className="flex flex-col gap-8">
            {SOURCE_GROUPS.map((group) => (
              <SourceGroup key={group.label} group={group} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function SourceGroup({ group }: { group: { label: string; ids: string[] } }) {
  const [activeId, setActiveId] = useState(group.ids[0]);
  const active = ECON_SOURCES.find((s) => s.id === activeId) ?? ECON_SOURCES.find((s) => s.id === group.ids[0])!;

  return (
    <div className="rounded-xl border border-border/10 bg-[#0f0f0f]/40 overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-4 bg-accent/20 border-b border-border/10">
        <span className="font-serif text-lg md:text-xl font-semibold tracking-tight text-foreground">{group.label}</span>
        <span className="h-px flex-1 bg-border/20" />
        <span className="font-mono text-[10px] text-muted-foreground">{group.ids.length} sources</span>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1.5 overflow-x-auto scrollbar-hide px-4 py-3 border-b border-border/10">
        {group.ids.map((id) => {
          const s = ECON_SOURCES.find((x) => x.id === id);
          if (!s) return null;
          const isActive = s.id === activeId;
          return (
            <button
              key={s.id}
              onClick={() => setActiveId(s.id)}
              aria-pressed={isActive}
              className={`h-8 px-3.5 rounded-lg border font-mono text-[11px] whitespace-nowrap transition-colors cursor-pointer ${
                isActive
                  ? 'bg-primary/10 border-primary text-primary'
                  : 'border-border/30 text-muted-foreground hover:border-foreground hover:text-foreground'
              }`}
            >
              {s.label}
              {s.keyRequired && <span className="ml-1 text-[8px] opacity-60">KEY</span>}
            </button>
          );
        })}
      </div>

      {/* Active source panel */}
      <div className="p-5">
        <EconPanel key={active.id} source={active} />
      </div>
    </div>
  );
}

function SectionHead({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-6">
      <p className="text-[13px] font-semibold uppercase tracking-[0.05em] text-foreground">{title}</p>
      <p className="text-[12px] text-muted-foreground mt-1 max-w-[60ch] leading-relaxed">{desc}</p>
      <div className="mt-3 h-px bg-border/20" />
    </div>
  );
}
