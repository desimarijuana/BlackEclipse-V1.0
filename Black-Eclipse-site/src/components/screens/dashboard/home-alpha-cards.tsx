'use client';

import type { ReactNode } from 'react';
import {
  ArrowUpRight,
  Activity,
  Bell,
  BookOpen,
  CalendarDays,
  ChevronDown,
  FileText,
  Layers,
  RefreshCw,
  TrendingUp,
} from '@/lib/icons';
import { navigateTo } from '@/lib/sdk/navigate';
import { cn } from '@/lib/utils';
import type { HomeData } from '@/lib/dashboard/use-home-data';
import type { HoldingState } from '@/lib/dashboard/home-model';
import { greetingFor } from '@/lib/dashboard/home-prefs';
import {
  ChangeText,
  DualSpark,
  Eyebrow,
  HomeCard,
  Pill,
  SectorDonut,
  SECTOR_COLORS,
  StatTile,
  SymbolChip,
  TONE_TEXT,
  UnavailableNote,
  WeightBar,
  formatAge,
  formatCompactMoney,
  formatMoney,
  formatPct,
  formatSignedPct,
  toneForChange,
} from './home-primitives';

const STATE_LABEL: Record<HoldingState, string> = {
  healthy: 'Healthy',
  sideways: 'Sideways',
  broken: 'Broken',
  falling: 'Falling',
  unknown: 'Unclassified',
};

const STATE_TONE: Record<HoldingState, string> = {
  healthy: 'text-emerald-400',
  sideways: 'text-zinc-300',
  broken: 'text-zinc-400',
  falling: 'text-rose-400',
  unknown: 'text-muted-foreground',
};

function openChart(symbol: string) {
  navigateTo({ tab: 'chart', params: { symbol } });
}

function Action({
  children,
  onClick,
  variant = 'ghost',
}: {
  children: ReactNode;
  onClick: () => void;
  variant?: 'ghost' | 'primary';
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.12em] transition-colors',
        variant === 'primary'
          ? 'bg-white/10 text-white hover:bg-white/15'
          : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
      )}
    >
      {children}
      <ArrowUpRight size={11} />
    </button>
  );
}

function SectionTitle({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-3">
      <h3 className="text-sm font-medium tracking-tight text-foreground">{title}</h3>
      {right}
    </div>
  );
}

export function GreetingHeader({ data }: { data: HomeData }) {
  return (
    <header className="flex flex-col gap-4 pb-1">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>Today</Eyebrow>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground md:text-[2rem]">
            {greetingFor()}
          </h1>
          <p className="mt-1 max-w-[42rem] text-xs leading-relaxed text-muted-foreground">
            Your book, the market and the news that matter — read from the JDDS vault.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">
            {data.updatedAt ? `JDDS · refreshed ${formatAge(data.updatedAt)}` : 'Connecting · JDDS'}
          </span>
          <div className="relative">
            <label htmlFor="home-market" className="sr-only">Dashboard market</label>
            <select
              id="home-market"
              value={data.market}
              onChange={(event) => data.setMarket(event.target.value)}
              className="h-9 min-w-[10.5rem] cursor-pointer appearance-none rounded-xl bg-white/[0.03] pl-3 pr-8 text-[11px] font-medium text-foreground outline-none transition-colors hover:bg-white/[0.06] focus-visible:bg-white/[0.06]"
            >
              {data.marketOptions.map((option) => (
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
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/[0.03] text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw size={14} className={cn(data.loading && 'animate-spin')} />
          </button>
        </div>
      </div>
    </header>
  );
}

export function PortfolioValueCard({ data }: { data: HomeData }) {
  if (data.holdingsCount === 0) {
    return (
      <HomeCard>
        <SectionTitle title="Portfolio value" />
        <UnavailableNote className="mt-4">
          No open holdings in this workspace. Add a position to see your book, day change and benchmark.
        </UnavailableNote>
        <div className="mt-3">
          <Action onClick={() => navigateTo({ tab: 'portfolio' })} variant="primary">Open portfolio</Action>
        </div>
      </HomeCard>
    );
  }
  const series = data.portfolioSeries;
  return (
    <HomeCard>
      <SectionTitle
        title="Portfolio value"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">{data.displayCurrency}</span>}
      />
      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-3xl font-semibold tracking-tight tabular-nums text-foreground md:text-4xl">
            {data.positionsLoading ? '…' : formatMoney(data.portfolioValue, data.displayCurrency)}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {data.positionsLoading ? (
              <span className="text-muted-foreground/70">Loading positions…</span>
            ) : (
              <>
                <span className={cn('font-medium', TONE_TEXT[toneForChange(data.portfolioReturnPct)])}>{formatSignedPct(data.portfolioReturnPct)}</span>
                {' '}on what you hold
              </>
            )}
          </p>
        </div>
        <div className="grid grid-cols-3 gap-5 text-right">
          <div>
            <p className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">Last day</p>
            <p className="mt-1 text-sm font-medium tabular-nums">{data.positionsLoading ? <span className="text-muted-foreground/70">…</span> : <ChangeText value={data.portfolioChangePct} />}</p>
            <p className="text-[9px] text-muted-foreground/60">{data.positionsLoading ? '—' : formatCompactMoney(data.portfolioChangeValue, data.displayCurrency)}</p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">Holdings</p>
            <p className="mt-1 text-sm font-medium tabular-nums text-foreground">{data.holdingsCount}</p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">Cost basis</p>
            <p className="mt-1 text-sm font-medium tabular-nums text-foreground">{formatCompactMoney(data.portfolioCostBasis, data.displayCurrency)}</p>
          </div>
        </div>
      </div>
      <div className="relative mt-4 h-28">
        {data.positionsLoading || data.historyLoading ? (
          <div className="h-full w-full animate-pulse rounded-xl bg-white/[0.03]" />
        ) : (
          <DualSpark
            portfolio={series.map((point) => point.portfolio)}
            benchmark={series.map((point) => point.benchmark)}
            className="h-full w-full"
          />
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[9px] uppercase tracking-[0.12em] text-muted-foreground/50">
        <span className="inline-flex items-center gap-3">
          <span className="inline-flex items-center gap-1"><span className="h-1.5 w-4 rounded-full bg-emerald-400" />You</span>
          <span className="inline-flex items-center gap-1"><span className="h-1.5 w-4 rounded-full bg-white/35" />S&amp;P 500</span>
        </span>
        <span>{series.length > 0 ? `${series[0].date.slice(5)} → ${series[series.length - 1].date.slice(5)}` : 'benchmark unavailable'}</span>
      </div>
      <div className="mt-3">
        <Action onClick={() => navigateTo({ tab: 'portfolio' })}>Open portfolio</Action>
      </div>
    </HomeCard>
  );
}

export function FeedCard({ data }: { data: HomeData }) {
  const items = data.feed.slice(0, 5);
  return (
    <HomeCard>
      <SectionTitle
        title={`My feed · ${new Date().toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short' })}`}
        right={(
          <div className="flex items-center gap-2">
            {data.feedNewCount > 0 && <Pill tone="neutral">{data.feedNewCount} new</Pill>}
            {data.feedNewCount > 0 && (
              <button type="button" onClick={data.markFeedSeen} className="text-[10px] text-muted-foreground hover:text-foreground">
                Mark read
              </button>
            )}
          </div>
        )}
      />
      {data.feedLoading ? (
        <div className="mt-4 space-y-2">
          {[0, 1, 2].map((row) => <div key={row} className="h-12 animate-pulse rounded-xl bg-white/[0.03]" />)}
        </div>
      ) : items.length === 0 ? (
        <div className="mt-4 rounded-xl bg-white/[0.02] px-3 py-3 text-[11px] text-muted-foreground">
          You’re caught up. Nothing new in your book since the last visit.
          <button type="button" onClick={() => navigateTo({ tab: 'news' })} className="ml-1 text-foreground underline decoration-white/20 underline-offset-2">
            See the whole market
          </button>
        </div>
      ) : (
        <div className="mt-3 divide-y divide-white/5">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => item.symbol ? openChart(item.symbol) : navigateTo({ tab: 'news' })}
              className="flex w-full items-start gap-3 py-2.5 text-left"
            >
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/[0.04] text-muted-foreground">
                {item.kind === 'alert' ? <Bell size={13} /> : item.kind === 'earnings' ? <CalendarDays size={13} /> : item.kind === 'sector' ? <Activity size={13} /> : <FileText size={13} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-1.5">
                  {item.symbol && <SymbolChip symbol={item.symbol} onClick={() => openChart(item.symbol!)} />}
                  <span className="text-[9px] uppercase tracking-[0.1em] text-muted-foreground/60">{item.tag}</span>
                  <span className="text-[9px] text-muted-foreground/40">{formatAge(item.at)}</span>
                </span>
                <span className="mt-0.5 block line-clamp-2 text-[12px] leading-snug text-foreground/90">{item.title}</span>
                {item.detail && <span className="mt-0.5 block truncate text-[10px] text-muted-foreground/70">{item.detail}</span>}
              </span>
            </button>
          ))}
        </div>
      )}
      <div className="mt-2">
        <Action onClick={() => navigateTo({ tab: 'news' })}>See the whole market</Action>
      </div>
    </HomeCard>
  );
}

export function HoldingsHealthCard({ data }: { data: HomeData }) {
  const health = data.holdingsHealth;
  const states: HoldingState[] = ['healthy', 'sideways', 'broken', 'falling'];
  return (
    <HomeCard>
      <SectionTitle
        title="How your holdings stand"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">{health.total} holdings</span>}
      />
      {data.historyLoading ? (
        <div className="mt-4 h-20 animate-pulse rounded-xl bg-white/[0.03]" />
      ) : health.total === 0 ? (
        <UnavailableNote className="mt-4">No open holdings. Add positions to classify the book.</UnavailableNote>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-5">
            {states.map((state) => (
              <div key={state}>
                <p className={cn('text-xl font-semibold tabular-nums', STATE_TONE[state])}>{health.counts[state]}</p>
                <p className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">{STATE_LABEL[state]}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-white/[0.06]">
            {states.map((state) => (
              <div key={state} style={{ width: `${health.weight[state] || 0}%`, backgroundColor: state === 'healthy' ? '#34d399' : state === 'sideways' ? '#e4e4e7' : state === 'broken' ? '#71717a' : '#fb7185' }} />
            ))}
          </div>
          {health.turningWeak && (
            <p className="mt-3 text-[11px] text-muted-foreground">
              Closest to turning weak: <span className="text-foreground">{health.turningWeak.symbol}</span>, {formatPct(health.turningWeak.distanceToWeakPct ?? 0, 1)} above its 50-day average.
            </p>
          )}
          <div className="mt-3 divide-y divide-white/5">
            {health.rows.slice(0, 4).map((row) => (
              <button key={row.symbol} type="button" onClick={() => openChart(row.symbol)} className="flex w-full items-center gap-3 py-2 text-left">
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] font-medium text-foreground">{row.symbol}</span>
                  <span className="block truncate text-[10px] text-muted-foreground/70">
                    {row.fallingDays > 0 ? `Falling for ${row.fallingDays} day${row.fallingDays === 1 ? '' : 's'}` : STATE_LABEL[row.state]}
                    {row.unrealizedPct != null ? ` · ${formatSignedPct(row.unrealizedPct)} on cost` : ''}
                  </span>
                </span>
                <span className={cn('text-[10px] font-medium uppercase tracking-[0.1em]', STATE_TONE[row.state])}>{STATE_LABEL[row.state]}</span>
              </button>
            ))}
          </div>
        </>
      )}
      <div className="mt-3">
        <Action onClick={() => navigateTo({ tab: 'portfolio' })}>Review portfolio</Action>
      </div>
    </HomeCard>
  );
}

export function WeekCard({ data }: { data: HomeData }) {
  const today = new Date();
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() + index);
    return date;
  });
  return (
    <HomeCard>
      <SectionTitle title="This week for you" right={<CalendarDays size={14} className="text-white/50" />} />
      <div className="mt-3 grid grid-cols-7 gap-1">
        {days.map((date, index) => (
          <div key={date.toISOString()} className={cn('rounded-lg px-1 py-2 text-center', index === 0 && 'bg-white/[0.07]')}>
            <p className="text-[8px] uppercase tracking-[0.1em] text-muted-foreground/60">{date.toLocaleDateString('en-US', { weekday: 'short' })}</p>
            <p className="mt-0.5 text-[12px] tabular-nums text-foreground/80">{date.getDate()}</p>
          </div>
        ))}
      </div>
      {data.weekEvents.length === 0 ? (
        <div className="mt-3 rounded-xl bg-white/[0.02] px-3 py-3 text-[11px] text-muted-foreground">
          No confirmed company events for your book this week.
          <button type="button" onClick={() => navigateTo({ tab: 'economics' })} className="ml-1 text-foreground underline decoration-white/20 underline-offset-2">
            Open the calendar
          </button>
        </div>
      ) : (
        <div className="mt-3 divide-y divide-white/5">
          {data.weekEvents.map((event) => (
            <button
              key={event.id}
              type="button"
              onClick={() => event.symbol ? openChart(event.symbol) : navigateTo({ tab: 'economics' })}
              className="flex w-full items-start gap-3 py-2.5 text-left"
            >
              <span className="w-16 shrink-0 text-[9px] uppercase tracking-[0.1em] text-muted-foreground/60">{event.dayLabel}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[12px] text-foreground/90">{event.title}</span>
                <span className="block truncate text-[10px] text-muted-foreground/70">{event.subtitle}</span>
              </span>
              <span className="shrink-0 text-[9px] uppercase tracking-[0.1em] text-muted-foreground/50">{event.tag}</span>
            </button>
          ))}
        </div>
      )}
      <div className="mt-2">
        <Action onClick={() => navigateTo({ tab: 'economics' })}>Open calendar</Action>
      </div>
    </HomeCard>
  );
}

export function MarketPulseCard({ data }: { data: HomeData }) {
  const pulse = data.pulse;
  return (
    <HomeCard>
      <SectionTitle
        title="What moved in the market"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">{pulse.scopeLabel}</span>}
      />
      <div className="mt-4 grid grid-cols-3 gap-2">
        <StatTile label="Market" value={<ChangeText value={pulse.indexChange} />} sub="latest session" />
        <StatTile label="Advancing" value={pulse.advancing} tone="bullish" sub={`${pulse.tracked} tracked`} />
        <StatTile label="Declining" value={pulse.declining} tone="bearish" sub={`${pulse.tracked} tracked`} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {pulse.leading && (
          <span>
            Leading: <span className="text-foreground">{pulse.leading.name}</span>{' '}
            <span className={TONE_TEXT[toneForChange(pulse.leading.change)]}>{formatSignedPct(pulse.leading.change)}</span>
          </span>
        )}
        <span>{pulse.tracked > 0 ? `${pulse.advancing} up · ${pulse.declining} down` : 'breadth unavailable'}</span>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">Sectors</p>
          <div className="mt-1.5 space-y-1.5">
            {pulse.sectors.slice(0, 4).map((sector) => (
              <div key={sector.name} className="flex items-center justify-between gap-2 text-[11px]">
                <span className="truncate text-muted-foreground">{sector.name}</span>
                <span className={cn('shrink-0 tabular-nums', TONE_TEXT[toneForChange(sector.change)])}>{formatSignedPct(sector.change)}</span>
              </div>
            ))}
            {pulse.sectors.length === 0 && <p className="text-[10px] text-muted-foreground/60">Unavailable</p>}
          </div>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">Movers</p>
          <div className="mt-1.5 space-y-1.5">
            {pulse.movers.slice(0, 4).map((mover) => (
              <button key={`${mover.symbol}-${mover.market}`} type="button" onClick={() => openChart(mover.symbol)} className="flex w-full items-center justify-between gap-2 text-left text-[11px]">
                <span className="min-w-0 truncate"><span className="text-foreground/90">{mover.symbol}</span> <span className="text-muted-foreground/60">{mover.market}</span></span>
                <span className={cn('shrink-0 tabular-nums', TONE_TEXT[toneForChange(mover.changePct)])}>{formatSignedPct(mover.changePct)}</span>
              </button>
            ))}
            {pulse.movers.length === 0 && <p className="text-[10px] text-muted-foreground/60">Unavailable</p>}
          </div>
        </div>
      </div>
      <div className="mt-3">
        <Action onClick={() => navigateTo({ tab: 'heatmap' })}>Market Pulse</Action>
      </div>
    </HomeCard>
  );
}

export function ResultsSeasonCard({ data }: { data: HomeData }) {
  const season = data.resultsSeason;
  return (
    <HomeCard>
      <SectionTitle
        title="Results season"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">{season.source}</span>}
      />
      {season.upcoming === 0 ? (
        <div className="mt-4 rounded-xl bg-white/[0.02] px-3 py-3 text-[11px] text-muted-foreground">
          No upcoming results are available from the earnings provider.
          <span className="ml-1 text-muted-foreground/60">Profit direction is not shown unless actual and prior-year figures exist.</span>
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <StatTile label="Upcoming" value={season.upcoming.toLocaleString()} sub="confirmed dates" />
            <StatTile label="Next 7 days" value={season.next7.toLocaleString()} sub="reports" />
          </div>
          <div className="mt-3 divide-y divide-white/5">
            {season.windows.map((window) => (
              <div key={window.date} className="flex items-center gap-3 py-2">
                <span className="w-20 shrink-0 text-[9px] uppercase tracking-[0.1em] text-muted-foreground/60">{window.label}</span>
                <span className="flex flex-1 flex-wrap gap-1">
                  {window.symbols.map((symbol) => <SymbolChip key={`${window.date}-${symbol}`} symbol={symbol} onClick={() => openChart(symbol)} />)}
                </span>
                <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground/60">{window.count}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[9px] text-muted-foreground/50">Profit up/down is unavailable unless JDDS has actual and prior-year figures.</p>
        </>
      )}
      <div className="mt-3">
        <Action onClick={() => navigateTo({ tab: 'discovery' })}>Open screener</Action>
      </div>
    </HomeCard>
  );
}

export function LeadersCard({ data }: { data: HomeData }) {
  return (
    <HomeCard>
      <SectionTitle
        title="Leaders you don’t hold"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">Eclipse momentum</span>}
      />
      {data.leaders.length === 0 ? (
        <UnavailableNote className="mt-4">No leader data is available for this scope right now.</UnavailableNote>
      ) : (
        <div className="mt-3 divide-y divide-white/5">
          {data.leaders.map((leader) => (
            <button key={`${leader.symbol}-${leader.marketId}`} type="button" onClick={() => openChart(leader.symbol)} className="flex w-full items-center gap-3 py-2.5 text-left">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/[0.06] text-[11px] font-semibold tabular-nums text-foreground">{leader.score}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[12px] font-medium text-foreground">{leader.symbol}</span>
                <span className="block truncate text-[10px] text-muted-foreground/70">{leader.name} · {leader.market}</span>
                <span className="mt-1 block h-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <span className="block h-full rounded-full bg-white/60" style={{ width: `${leader.score}%` }} />
                </span>
              </span>
              <span className="shrink-0 text-right">
                <ChangeText value={leader.changePct} className="text-[10px]" />
                <span className="mt-0.5 block text-[9px] text-muted-foreground/50">{leader.reason}</span>
              </span>
            </button>
          ))}
        </div>
      )}
      <div className="mt-3">
        <Action onClick={() => navigateTo({ tab: 'discovery' })}>Open screener</Action>
      </div>
    </HomeCard>
  );
}

export function ResearchCard({ data }: { data: HomeData }) {
  return (
    <HomeCard>
      <SectionTitle title="Research on your holdings" right={<BookOpen size={14} className="text-white/50" />} />
      {data.research.length === 0 ? (
        <div className="mt-4 rounded-xl bg-white/[0.02] px-3 py-3 text-[11px] text-muted-foreground">
          No saved research for your book yet.
          <button
            type="button"
            onClick={() => navigateTo({ tab: 'chat', params: { prompt: 'Research my holdings and summarise the key risks and catalysts.' } })}
            className="ml-1 text-foreground underline decoration-white/20 underline-offset-2"
          >
            Ask Eclipse
          </button>
        </div>
      ) : (
        <div className="mt-3 divide-y divide-white/5">
          {data.research.map((row) => (
            <button
              key={row.id}
              type="button"
              onClick={() => navigateTo({ tab: 'chat', params: { prompt: `Summarise the thesis for ${row.symbol} and what would change it.` } })}
              className="flex w-full items-start gap-3 py-2.5 text-left"
            >
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-1.5">
                  <SymbolChip symbol={row.symbol} onClick={() => openChart(row.symbol)} />
                  <span className="text-[9px] uppercase tracking-[0.1em] text-muted-foreground/60">{row.watching ? 'Watching' : 'Held'}</span>
                  <span className="text-[9px] text-muted-foreground/40">{formatAge(row.updatedAt)}</span>
                </span>
                <span className="mt-1 block line-clamp-2 text-[12px] leading-snug text-foreground/90">{row.title}</span>
              </span>
              <span className="shrink-0 text-[9px] uppercase tracking-[0.1em] text-muted-foreground/50">{row.status}</span>
            </button>
          ))}
        </div>
      )}
      <div className="mt-2">
        <Action onClick={() => navigateTo({ tab: 'chat', params: { prompt: 'Research my holdings and summarise the key risks and catalysts.' } })}>Ask Eclipse</Action>
      </div>
    </HomeCard>
  );
}

export function SectorExposureCard({ data }: { data: HomeData }) {
  const concentration = data.concentration;
  return (
    <HomeCard>
      <SectionTitle title="What you hold, by sector" right={<Layers size={14} className="text-white/50" />} />
      {data.holdingsCount === 0 || concentration.sectorCount === 0 ? (
        <UnavailableNote className="mt-4">Sector exposure is unavailable for this workspace.</UnavailableNote>
      ) : (
        <div className="mt-3 flex items-center gap-4">
          <SectorDonut slices={concentration.slices} />
          <div className="min-w-0 flex-1 space-y-2">
            {concentration.slices.slice(0, 4).map((slice, index) => (
              <div key={slice.name}>
                <div className="flex items-center justify-between gap-2 text-[10px]">
                  <span className="inline-flex min-w-0 items-center gap-1.5 text-muted-foreground">
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: SECTOR_COLORS[index % SECTOR_COLORS.length] }} />
                    <span className="truncate">{slice.name}</span>
                  </span>
                  <span className="shrink-0 tabular-nums text-foreground/80">{formatPct(slice.weightPct)}</span>
                </div>
                <WeightBar className="mt-1" value={slice.weightPct} color={SECTOR_COLORS[index % SECTOR_COLORS.length]} />
              </div>
            ))}
          </div>
        </div>
      )}
      {concentration.sectorCount > 0 && (
        <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground/70">
          {concentration.diversified ? `Diversified across ${concentration.sectorCount} sectors.` : `Top exposure: ${concentration.topSector ?? '—'} at ${formatPct(concentration.topSharePct)}.`}
        </p>
      )}
      <div className="mt-2">
        <Action onClick={() => navigateTo({ tab: 'portfolio' })}>Know what you own</Action>
      </div>
    </HomeCard>
  );
}

export function TrackRecordCard({ data }: { data: HomeData }) {
  const record = data.record;
  return (
    <HomeCard>
      <SectionTitle title="Track record" right={<TrendingUp size={14} className="text-white/50" />} />
      {!record.hasData ? (
        <div className="mt-4 rounded-xl bg-white/[0.02] px-3 py-3 text-[11px] text-muted-foreground">
          Not enough finished signals yet. Your journal and closed theses will appear here.
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatTile label="Win rate" value={`${Math.round(record.winRate * 100)}%`} sub={`${record.totalTrades} trades`} />
          <StatTile label="Net P&L" value={formatCompactMoney(record.netPnl, 'USD')} tone={toneForChange(record.netPnl)} sub="journal" />
          <StatTile label="Profit factor" value={record.profitFactor.toFixed(2)} sub="journal" />
          <StatTile label="Theses" value={`${record.activeTheses}/${record.closedTheses}`} sub="active / closed" />
        </div>
      )}
      <p className="mt-3 text-[9px] leading-relaxed text-muted-foreground/50">
        This is your recorded journal and thesis history, not a proprietary model track record. Past results don’t promise future returns.
      </p>
      <div className="mt-2">
        <Action onClick={() => navigateTo({ tab: 'journal' })}>Open journal</Action>
      </div>
    </HomeCard>
  );
}

export function HomeFooter() {
  return (
    <footer className="mt-2 flex flex-col gap-2 rounded-3xl bg-white/[0.015] px-4 py-3 text-[10px] text-muted-foreground/60 md:px-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {[
          { label: 'Screener', tab: 'discovery' as const },
          { label: 'Market Pulse', tab: 'heatmap' as const },
          { label: 'Portfolio', tab: 'portfolio' as const },
          { label: 'News', tab: 'news' as const },
          { label: 'Journal', tab: 'journal' as const },
          { label: 'Alerts', tab: 'alerts' as const },
        ].map((link) => (
          <button key={link.tab} type="button" onClick={() => navigateTo({ tab: link.tab })} className="hover:text-foreground">
            {link.label}
          </button>
        ))}
      </div>
      <p className="max-w-[70rem] leading-relaxed">
        Eclipse is a research workspace, not an investment advisory service. Figures come from JDDS and connected providers; unavailable inputs are labelled rather than estimated. Past results do not promise future returns.
      </p>
    </footer>
  );
}
