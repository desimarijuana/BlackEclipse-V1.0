'use client';

import React, { useState } from 'react';
import { Globe } from 'lucide-react';
import { ECON_SOURCES } from '@/lib/economics/sources';
import { EconPanel } from './panel';
import { SnapshotView } from './snapshot';
import { CalendarView } from './calendar';

// Group the source registry into the reference's taxonomy for the picker sidebar.
const SOURCE_GROUPS: { label: string; ids: string[] }[] = [
  { label: 'Multilateral', ids: ['worldbank', 'imf', 'fred', 'fred-analytics', 'oecd', 'ecb', 'eurostat'] },
  { label: 'US agencies', ids: ['bls', 'census', 'fiscaldata', 'bea', 'nber', 'federalreserve'] },
  { label: 'Market / commercial', ids: ['trading-economics', 'economic-calendar', 'econdb', 'bis', 'cftc', 'eia', 'wto'] },
  { label: 'National stats', ids: ['ons-uk', 'bcb', 'akshare-china', 'statcan'] },
  { label: 'International / thematic', ids: ['central-banks', 'ilo', 'un-comtrade', 'wb-health', 'adb', 'unesco', 'owid', 'fincept-macro'] },
];

const GROUP_ORDER = SOURCE_GROUPS.map((g) => g.label);

export function EconomicsScreen() {
  const [activeSource, setActiveSource] = useState(ECON_SOURCES[0].id);

  const active = ECON_SOURCES.find((s) => s.id === activeSource) ?? ECON_SOURCES[0];

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

        {/* ── 01 · SNAPSHOT ─────────────────────────────────────── */}
        <section className="border-t border-border/10 pt-8">
          <SectionHead
            num="01 / SNAPSHOT"
            title="Global macro · live vintages"
            desc="Every value carries its source and “as of” vintage — pulled from the FRED public CSV feed. Nothing fabricated."
          />
          <SnapshotView />
        </section>

        {/* ── 02 · EXPLORER ────────────────────────────────────── */}
        <section className="border-t border-border/10 pt-8">
          <SectionHead
            num="02 / EXPLORER"
            title="Time-series explorer"
            desc="Pick a source, country, indicator and series to chart its history across 30+ data providers."
          />
          <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-8 items-start">
            {/* Source picker sidebar */}
            <aside className="rounded-xl bg-[#0f0f0f]/60 border border-border/10 p-5 lg:sticky lg:top-4">
              <h3 className="text-[13px] font-semibold text-foreground mb-3">Data source</h3>
              <div className="flex flex-col">
                {GROUP_ORDER.map((group) => {
                  const ids = SOURCE_GROUPS.find((g) => g.label === group)!.ids;
                  return (
                    <div key={group} className="py-2.5 first:pt-0 border-t border-border/10 first:border-0">
                      <span className="block font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground mb-2">
                        {group}
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {ids.map((id) => {
                          const s = ECON_SOURCES.find((x) => x.id === id);
                          if (!s) return null;
                          const isActive = s.id === activeSource;
                          return (
                            <button
                              key={s.id}
                              onClick={() => setActiveSource(s.id)}
                              title={s.description || s.label}
                              aria-pressed={isActive}
                              className={`relative h-[30px] px-3 rounded-lg border font-mono text-[11px] transition-colors cursor-pointer ${
                                isActive
                                  ? 'bg-primary/10 border-primary text-primary pl-4'
                                  : 'border-border/30 text-muted-foreground hover:border-foreground hover:text-foreground'
                              }`}
                            >
                              {isActive && (
                                <span className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1 h-1 rounded-full bg-primary" />
                              )}
                              {s.label}
                              {s.keyRequired && <span className="ml-1 text-[8px] opacity-60">KEY</span>}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </aside>

            {/* Controls + chart */}
            <div className="min-w-0">
              <EconPanel key={active.id} source={active} />
            </div>
          </div>
        </section>

        {/* ── 03 · CALENDAR ─────────────────────────────────────── */}
        <section className="border-t border-border/10 pt-8">
          <SectionHead
            num="03 / CALENDAR"
            title="Upcoming releases"
            desc="Schedule only · no fabricated numbers. Forecasts appear only when a real consensus exists."
          />
          <CalendarView />
        </section>
      </div>
    </div>
  );
}

function SectionHead({ num, title, desc }: { num: string; title: string; desc: string }) {
  return (
    <div className="flex items-end justify-between gap-4 mb-6 flex-wrap">
      <div>
        <span className="font-mono text-[12px] text-primary tracking-[0.05em]">{num}</span>
        <p className="text-[13px] font-semibold uppercase tracking-[0.05em] text-muted-foreground mt-1">{title}</p>
      </div>
      <p className="text-[13px] text-muted-foreground max-w-[46ch] text-right leading-relaxed">{desc}</p>
    </div>
  );
}
