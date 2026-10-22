'use client';

import { useMemo } from 'react';
import { ChevronDown, RefreshCw, Shield } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { HOME_MARKETS, useHomeData } from '@/lib/dashboard/use-home-data';
import {
  AlertsCard,
  AttentionCard,
  ConcentrationCard,
  DashboardFooter,
  LeadershipCard,
  MarketHero,
  MarketTapeStrip,
  PortfolioHealthCard,
  PortfolioWatchCard,
  RegimeCard,
  UniverseCard,
  WatchlistRadarCard,
} from './home-cards';
import { Eyebrow } from './home-primitives';

function DashboardSkeleton() {
  return (
    <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-12">
      {[
        'md:col-span-2 lg:col-span-7 min-h-[330px]',
        'md:col-span-2 lg:col-span-5 min-h-[330px]',
        'md:col-span-1 lg:col-span-4 min-h-[280px]',
        'md:col-span-2 lg:col-span-8 min-h-[280px]',
        'md:col-span-2 lg:col-span-6 min-h-[210px]',
        'md:col-span-1 lg:col-span-3 min-h-[210px]',
        'md:col-span-1 lg:col-span-3 min-h-[210px]',
      ].map((className, index) => (
        <div key={index} className={cn('glass-card rounded-2xl border border-white/10 p-5', className)}>
          <div className="h-2 w-24 animate-pulse rounded bg-white/10" />
          <div className="mt-4 h-7 w-3/5 animate-pulse rounded bg-white/[0.08]" />
          <div className="mt-3 h-3 w-4/5 animate-pulse rounded bg-white/[0.05]" />
          <div className="mt-8 h-24 w-full animate-pulse rounded-xl bg-white/[0.04]" />
        </div>
      ))}
    </div>
  );
}

export function HomeDashboardScreen({ active = true }: { active?: boolean }) {
  const data = useHomeData(active);
  const firstLoad = data.loading && data.updatedAt == null;
  const marketOptions = useMemo(() => HOME_MARKETS, []);

  return (
    <div className="relative mx-auto w-full max-w-[1560px] px-1 pb-24 md:px-2">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-24 h-72 bg-[radial-gradient(60%_100%_at_50%_0%,rgba(255,255,255,0.06),transparent_70%)]"
      />
      <div className="relative">
        <header className="flex flex-wrap items-end justify-between gap-3 pb-3">
          <div>
            <Eyebrow>Eclipse daily dashboard</Eyebrow>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground md:text-[1.75rem]">Dashboard</h1>
            <p className="mt-1 max-w-[36rem] text-xs leading-relaxed text-muted-foreground">
              Market context, portfolio health and the names that need attention — read from the JDDS vault.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="hidden text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50 sm:inline">
              {data.updatedAt ? 'JDDS · refreshed' : 'Connecting · JDDS'}
            </span>
            <div className="relative">
              <label htmlFor="home-market" className="sr-only">Dashboard market</label>
              <select
                id="home-market"
                value={data.market}
                onChange={(event) => data.setMarket(event.target.value)}
                className="h-9 min-w-[11rem] cursor-pointer appearance-none rounded-xl border border-white/10 bg-background/60 pl-3 pr-8 text-[11px] font-medium text-foreground outline-none transition-colors hover:border-white/20 focus-visible:border-white/30"
              >
                {marketOptions.map((option) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
              <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            </div>
            <button
              type="button"
              onClick={data.refresh}
              disabled={data.loading}
              aria-label="Refresh dashboard"
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-background/60 text-muted-foreground transition-colors hover:border-white/20 hover:text-foreground disabled:opacity-50"
            >
              <RefreshCw size={14} className={cn(data.loading && 'animate-spin')} />
            </button>
          </div>
        </header>

        {data.loadError && (
          <div className="mb-3 flex items-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-3 py-2 text-[11px] text-foreground/80">
            <Shield size={13} className="shrink-0 text-white/60" />
            Some market feeds are unavailable right now. Cards below show only what JDDS actually returned — no fabricated values.
            <button type="button" onClick={data.refresh} className="ml-auto shrink-0 underline decoration-white/25 underline-offset-2 hover:text-white">
              Retry
            </button>
          </div>
        )}

        <div className="mb-3">
          <MarketTapeStrip data={data} />
        </div>

        {firstLoad ? (
          <DashboardSkeleton />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-12">
            <MarketHero data={data} />
            <PortfolioHealthCard data={data} />
            <LeadershipCard data={data} />
            <RegimeCard data={data} />
            <AttentionCard data={data} />
            <PortfolioWatchCard data={data} />
            <WatchlistRadarCard data={data} />
            <ConcentrationCard data={data} />
            <UniverseCard data={data} />
            <AlertsCard data={data} />
          </div>
        )}

        <div className="mt-4">
          <DashboardFooter data={data} />
        </div>
      </div>
    </div>
  );
}
