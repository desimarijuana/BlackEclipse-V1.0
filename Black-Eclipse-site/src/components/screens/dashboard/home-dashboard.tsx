'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Settings2, Shield } from '@/lib/icons';
import { useCommandStore } from '@/lib/search/store';
import { createQuickAlert } from '@/lib/alerts/quick-alert';
import { navigateTo } from '@/lib/sdk/navigate';
import { cn } from '@/lib/utils';
import { useHomeData } from '@/lib/dashboard/use-home-data';
import { useHomePrefs } from '@/lib/dashboard/home-prefs';
import {
  AlertsStripCard,
  ActionListCard,
  DataFreshness,
  FxExposureCard,
  MarketSessionsCard,
  PnlAttributionCard,
  RelativePerformanceCard,
  RiskCard,
  SectorRotationCard,
} from './home-alpha-insights';
import {
  FeedCard,
  GreetingHeader,
  HoldingsHealthCard,
  HomeFooter,
  LeadersCard,
  MarketPulseCard,
  PortfolioValueCard,
  ResearchCard,
  ResultsSeasonCard,
  SectorExposureCard,
  TrackRecordCard,
  WeekCard,
} from './home-alpha-cards';

type SectionKey =
  | 'feed' | 'health' | 'week' | 'pulse' | 'results' | 'leaders' | 'research'
  | 'sector' | 'record' | 'attribution' | 'actions' | 'sessions' | 'risk'
  | 'fx' | 'rotation' | 'relative' | 'alerts';

const SECTION_LABELS: Record<SectionKey, string> = {
  attribution: "What moved your book",
  actions: 'Needs a look',
  feed: 'My feed',
  health: 'How your holdings stand',
  sessions: 'Market sessions',
  pulse: 'What moved in the market',
  risk: 'Portfolio risk',
  rotation: 'Sector rotation',
  relative: 'Relative to benchmark',
  fx: 'Currency exposure',
  week: 'This week for you',
  results: 'Results season',
  leaders: 'Leaders you don’t hold',
  research: 'Research on your holdings',
  sector: 'What you hold, by sector',
  record: 'Track record',
  alerts: 'Alerts',
};

const INVESTOR_ORDER: SectionKey[] = ['attribution', 'feed', 'health', 'week', 'research', 'sector', 'results', 'pulse', 'rotation', 'risk', 'relative', 'leaders', 'record', 'fx', 'sessions', 'alerts'];
const TRADER_ORDER: SectionKey[] = ['pulse', 'rotation', 'actions', 'attribution', 'leaders', 'relative', 'feed', 'health', 'sessions', 'week', 'results', 'risk', 'research', 'sector', 'record', 'fx', 'alerts'];
const BOTH_ORDER: SectionKey[] = ['attribution', 'feed', 'health', 'actions', 'week', 'pulse', 'rotation', 'results', 'leaders', 'relative', 'research', 'sector', 'risk', 'fx', 'sessions', 'record', 'alerts'];

export function HomeDashboardScreen({ active = true }: { active?: boolean }) {
  const data = useHomeData(active);
  const { prefs, toggleSection, moveSection } = useHomePrefs();
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const defaultOrder = prefs.lens === 'trader' ? TRADER_ORDER : prefs.lens === 'investor' ? INVESTOR_ORDER : BOTH_ORDER;

  const order = useMemo(() => {
    const base = prefs.sectionOrder.length > 0 ? prefs.sectionOrder.filter((id): id is SectionKey => id in SECTION_LABELS) : defaultOrder;
    const complete = [...base];
    for (const key of defaultOrder) if (!complete.includes(key)) complete.push(key);
    return complete.filter((key) => !prefs.hiddenSections.includes(key));
  }, [prefs.sectionOrder, prefs.hiddenSections, defaultOrder]);

  const symbols = useMemo(() => {
    const list = [...data.actionList.map((row) => row.symbol), ...data.holdings.map((holding) => holding.symbol)];
    return [...new Set(list.map((symbol) => symbol.toUpperCase()))];
  }, [data.actionList, data.holdings]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === '/') {
        event.preventDefault();
        useCommandStore.getState().setOpen(true);
        return;
      }
      if (event.key.toLowerCase() === 'r') {
        data.refresh();
        return;
      }
      if (symbols.length === 0) return;
      if (event.key.toLowerCase() === 'j' || event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSelected((current) => {
          const index = current ? symbols.indexOf(current) : -1;
          const next = event.key.toLowerCase() === 'j' ? Math.min(symbols.length - 1, index + 1) : Math.max(0, index - 1);
          return symbols[next] ?? symbols[0];
        });
        return;
      }
      if (!selected) return;
      if (event.key === 'Enter') {
        navigateTo({ tab: 'chart', params: { symbol: selected } });
      } else if (event.key.toLowerCase() === 'a') {
        void createQuickAlert(selected, 3);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [data, selected, symbols]);

  const sections: Record<SectionKey, React.ReactNode> = {
    attribution: <PnlAttributionCard data={data} />,
    actions: <ActionListCard data={data} />,
    feed: <FeedCard data={data} />,
    health: <HoldingsHealthCard data={data} />,
    week: <WeekCard data={data} />,
    pulse: <MarketPulseCard data={data} />,
    results: <ResultsSeasonCard data={data} />,
    leaders: <LeadersCard data={data} />,
    research: <ResearchCard data={data} />,
    sector: <SectorExposureCard data={data} />,
    record: <TrackRecordCard data={data} />,
    sessions: <MarketSessionsCard data={data} />,
    risk: <RiskCard data={data} />,
    fx: <FxExposureCard data={data} />,
    rotation: <SectorRotationCard data={data} />,
    relative: <RelativePerformanceCard data={data} />,
    alerts: <AlertsStripCard data={data} />,
  };

  return (
    <div className="relative w-full px-2 pb-6 md:px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-24 h-72 bg-[radial-gradient(60%_100%_at_50%_0%,rgba(255,255,255,0.05),transparent_70%)]"
      />
      <div className="relative">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0 flex-1">
            <GreetingHeader data={data} />
          </div>
        </div>

        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {selected && (
              <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] uppercase tracking-[0.1em] text-foreground/80">
                Selected · {selected} <span className="text-muted-foreground/60">Enter open · A alert</span>
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => setCustomizeOpen((value) => !value)}
            className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground hover:bg-white/[0.05] hover:text-foreground"
          >
            <Settings2 size={12} /> Customize
          </button>
        </div>

        {customizeOpen && (
          <div className="mb-3 rounded-2xl bg-white/[0.03] p-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/60">Sections</p>
            <div className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
              {defaultOrder.map((key, index) => {
                const hidden = prefs.hiddenSections.includes(key);
                return (
                  <div key={key} className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/[0.03]">
                    <button
                      type="button"
                      onClick={() => toggleSection(key)}
                      className={cn('flex h-5 w-5 items-center justify-center rounded border text-[9px]', hidden ? 'border-white/15 text-transparent' : 'border-white/30 bg-white/10 text-white')}
                      aria-label={`${hidden ? 'Show' : 'Hide'} ${SECTION_LABELS[key]}`}
                    >
                      ✓
                    </button>
                    <span className={cn('min-w-0 flex-1 truncate text-[11px]', hidden ? 'text-muted-foreground/50 line-through' : 'text-foreground/85')}>{SECTION_LABELS[key]}</span>
                    <button type="button" onClick={() => moveSection(key, -1, defaultOrder)} disabled={index === 0} className="p-1 text-muted-foreground/60 hover:text-foreground disabled:opacity-30"><ChevronUp size={11} /></button>
                    <button type="button" onClick={() => moveSection(key, 1, defaultOrder)} disabled={index === defaultOrder.length - 1} className="p-1 text-muted-foreground/60 hover:text-foreground disabled:opacity-30"><ChevronDown size={11} /></button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {data.loadError && (
          <div className="mb-3 flex items-center gap-2 rounded-2xl bg-white/[0.04] px-3 py-2 text-[11px] text-foreground/80">
            <Shield size={13} className="shrink-0 text-white/60" />
            Some market feeds are unavailable right now. Cards below show only what JDDS actually returned — no fabricated values.
            <button type="button" onClick={data.refresh} className="ml-auto shrink-0 underline decoration-white/25 underline-offset-2 hover:text-white">
              Retry
            </button>
          </div>
        )}

        <PortfolioValueCard data={data} />

        <div className="mt-3 flex flex-col gap-3">
          {order.map((key) => <div key={key}>{sections[key]}</div>)}
        </div>

        <div className="mt-2">
          <DataFreshness data={data} />
        </div>
        <HomeFooter />
      </div>
    </div>
  );
}
