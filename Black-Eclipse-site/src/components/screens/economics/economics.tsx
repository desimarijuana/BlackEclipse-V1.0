'use client';

import React, { useState } from 'react';
import { Globe, LineChart, Activity, CalendarDays } from 'lucide-react';
import { TabBar } from '@/components/ui/tab-bar';
import { ECON_SOURCES } from '@/lib/economics/sources';
import { useSubroute } from '@/hooks/use-subroute';
import { EconPanel } from './panel';
import { SnapshotView } from './snapshot';
import { CalendarView } from './calendar';
import { DecisionDashboard } from './dashboard';

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
  const [section, setSection] = useState<'overview' | 'calendar' | 'explorer'>('overview');
  // Indicator focus dispatched by global search (e.g. 'NFP'), applied to the
  // calendar section. Cleared when the user changes sections away from it.
  const [calendarFocus, setCalendarFocus] = useState<string | undefined>(undefined);

  // Global search: 'economics.calendar' (+ optional indicator focus).
  useSubroute('economics', (req) => {
    if (req.subroute === 'calendar') {
      setSection('calendar');
      setCalendarFocus(req.focus);
    } else if (req.subroute === 'explorer') {
      setSection('explorer');
    } else if (req.subroute === 'overview') {
      setSection('overview');
    }
  });

  return (
    <div className="w-full px-4 md:px-8 py-8 h-full overflow-y-auto pb-20">
      <div className="animate-fade-in-up flex flex-col gap-6">
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

        {/* ── Section tabs ─────────────────────────────────────── */}
        <TabBar
          items={[
            { id: 'overview', label: 'Overview', icon: Activity },
            { id: 'calendar', label: 'Calendar', icon: CalendarDays },
            { id: 'explorer', label: 'Time-series Explorer', icon: LineChart },
          ]}
          activeId={section}
          onChange={(id) => {
            setSection(id as typeof section);
            if (id !== 'calendar') setCalendarFocus(undefined);
          }}
        />

        {section === 'overview' && (
          <div className="flex flex-col gap-10">
            <section>
              <SectionHead
                title="Global macro · live vintages"
                desc="Central-bank rates & key US prints, each with its “as of” vintage — pulled from the FRED public CSV feed. Nothing fabricated."
              />
              <SnapshotView />
            </section>

            <section className="border-t border-border/10 pt-8">
              <SectionHead
                title="Decision dashboard"
                desc="At-a-glance macro signals to guide positioning — real rate, yield curve, regime, policy stance and dollar."
              />
              <DecisionDashboard />
            </section>

            <section className="border-t border-border/10 pt-8">
              <SectionHead
                title="Economic calendar"
                desc="Schedule only · no fabricated numbers. Forecasts appear only when a real consensus exists."
              />
              <CalendarView />
            </section>
          </div>
        )}

        {section === 'calendar' && (
          <section>
            <SectionHead
              title="Economic calendar"
              desc="Schedule only · no fabricated numbers. Forecasts appear only when a real consensus exists."
            />
            <CalendarView focus={calendarFocus} />
          </section>
        )}

        {section === 'explorer' && (
          <section>
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
        )}
      </div>
    </div>
  );
}

function SourceGroup({ group }: { group: { label: string; ids: string[] } }) {
  const [activeId, setActiveId] = useState(group.ids[0]);
  const active = ECON_SOURCES.find((s) => s.id === activeId) ?? ECON_SOURCES.find((s) => s.id === group.ids[0])!;

  return (
    <div className="rounded-xl border border-border/10 glass-card-subtle overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-4 glass-card-subtle border-b border-border/10">
        <span className="font-serif text-lg md:text-xl font-semibold tracking-tight text-foreground">{group.label}</span>
        <span className="h-px flex-1 bg-border/20" />
        <span className="font-mono text-[10px] text-muted-foreground">{group.ids.length} sources</span>
      </div>

      {/* Tab bar */}
      <TabBar
        className="mb-0 rounded-none border-b border-border/10 px-4 py-3"
        items={group.ids
          .map((id) => ECON_SOURCES.find((x) => x.id === id))
          .filter((s): s is NonNullable<typeof s> => Boolean(s))
          .map((s) => ({
            id: s.id,
            label: (
              <>
                {s.label}
                {s.keyRequired && <span className="ml-1 text-[8px] opacity-60">KEY</span>}
              </>
            ),
          }))}
        activeId={activeId}
        onChange={setActiveId}
      />

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
