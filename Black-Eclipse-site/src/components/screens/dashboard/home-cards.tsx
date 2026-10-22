'use client';

import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  Briefcase,
  ChartLine,
  Globe,
  Layers,
  ScanEye,
  Sparkles,
  Star,
  Target,
  TrendingDown,
  TrendingUp,
} from '@/lib/icons';
import { navigateTo } from '@/lib/sdk/navigate';
import { cn } from '@/lib/utils';
import type { HomeData } from '@/lib/dashboard/use-home-data';
import {
  AreaSpark,
  CardTitle,
  ChangeText,
  ComponentMeter,
  Eyebrow,
  HealthRing,
  HomeCard,
  Pill,
  SectorDonut,
  SplitBar,
  StatTile,
  SymbolChip,
  TONE_TEXT,
  UnavailableNote,
  WeatherLine,
  WeightBar,
  formatAge,
  formatCompactMoney,
  formatPct,
  formatPrice,
  formatSignedPct,
  toneForChange,
  SECTOR_COLORS,
} from './home-primitives';

const TONE_LABEL = {
  bullish: 'Bullish',
  bearish: 'Bearish',
  neutral: 'Neutral',
  unavailable: 'Unavailable',
} as const;

function openChart(symbol: string) {
  navigateTo({ tab: 'chart', params: { symbol } });
}

function CtaButton({
  children,
  onClick,
  className,
}: {
  children: React.ReactNode;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.04] px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-white/80 transition-colors hover:border-white/30 hover:bg-white/[0.08] hover:text-white',
        className,
      )}
    >
      {children}
      <ArrowRight size={11} />
    </button>
  );
}

function GhostButton({
  children,
  onClick,
  className,
}: {
  children: React.ReactNode;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-foreground/80 transition-colors hover:border-white/20 hover:text-foreground',
        className,
      )}
    >
      {children}
      <ArrowUpRight size={11} />
    </button>
  );
}

export function MarketHero({ data }: { data: HomeData }) {
  const bias = TONE_LABEL[data.tone];
  const trackedWord = data.trackedLabel === 'markets' ? 'markets' : 'sectors';
  return (
    <HomeCard accent className="md:col-span-2 lg:col-span-7 min-h-[330px] justify-between">
      <div aria-hidden className="pointer-events-none absolute -right-10 -top-16 h-[260px] w-[75%] opacity-30">
        {data.benchmark && <AreaSpark values={data.benchmark.closes} stroke="#e5e7eb" className="h-full w-full" />}
      </div>
      <div className="relative">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Eyebrow>Market overview · {data.marketLabel}</Eyebrow>
          <div className="flex items-center gap-2">
            {data.includesDemo && <Pill tone="neutral">{data.demoOnly ? 'Demo book' : 'Includes demo'}</Pill>}
            <Pill tone={data.tone}>{bias}</Pill>
          </div>
        </div>
        <h2 className="mt-3 max-w-[30rem] text-3xl font-semibold leading-[1.08] tracking-tight text-foreground md:text-[2.6rem]">
          {data.brief.headline}
        </h2>
        <p className="mt-2.5 max-w-[34rem] text-[12px] leading-relaxed text-muted-foreground md:text-[13px]">
          {data.brief.detail}
        </p>
      </div>

      <div className="relative mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatTile label="Market bias" value={bias} tone={data.tone} sub={data.weatherSource === 'regime' ? data.regime?.label : 'Breadth-derived'} />
        <StatTile
          label={`${trackedWord} up`}
          value={`${data.breadth.advancing}/${data.breadth.tracked || '—'}`}
          tone={data.breadth.advancing > data.breadth.tracked / 2 ? 'bullish' : 'neutral'}
          sub={`${data.breadth.beating} beating benchmark`}
        />
        <StatTile
          label="Portfolio health"
          value={data.historyLoading ? '…' : data.health.score == null ? '—' : `${data.health.score}`}
          tone={data.historyLoading ? 'neutral' : data.health.score == null ? 'unavailable' : data.health.score >= 70 ? 'bullish' : data.health.score >= 55 ? 'neutral' : 'bearish'}
          sub={data.historyLoading ? 'loading trend history' : data.health.score == null ? 'history missing' : `${data.health.label} · ${data.holdingsCount} holdings`}
        />
        <StatTile
          label="Portfolio value"
          value={data.positionsLoading ? '…' : formatCompactMoney(data.portfolioValue, data.displayCurrency)}
          tone={data.positionsLoading ? 'neutral' : toneForChange(data.portfolioChangePct)}
          sub={data.positionsLoading ? 'loading live quotes' : `${formatSignedPct(data.portfolioChangePct)} today`}
        />
      </div>

      <div className="relative mt-4 flex flex-wrap items-center gap-2">
        <CtaButton onClick={() => navigateTo({ tab: 'portfolio' })}>Open portfolio</CtaButton>
        <GhostButton onClick={() => navigateTo({ tab: 'heatmap' })}>Market pulse</GhostButton>
        <span className="ml-auto text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">
          Refreshed {formatAge(data.updatedAt)}
        </span>
      </div>
    </HomeCard>
  );
}

export function PortfolioHealthCard({ data }: { data: HomeData }) {
  const mix = data.trendMix;
  const empty = data.holdingsCount === 0;
  const takeaway = mix.uptrend >= 50
    ? 'Uptrend exposure leads the book, showing constructive trend alignment.'
    : mix.downtrend >= 20
      ? 'Downtrend exposure is elevated; review the weakest holdings.'
      : mix.weakUptrend >= 40
        ? 'Weak uptrends dominate; the book is constructive but not fully aligned.'
        : 'Trend structure is mixed across the book.';
  return (
    <HomeCard className="md:col-span-2 lg:col-span-5 justify-between">
      <CardTitle
        eyebrow="Portfolio health"
        right={data.includesDemo ? <Pill tone="neutral">{data.demoOnly ? 'Demo' : 'Demo +'}</Pill> : undefined}
      />
      {empty ? (
        <div className="mt-4 flex flex-1 flex-col items-start justify-center gap-3">
          <UnavailableNote>
            No open holdings in {data.marketLabel}. Add a position or switch the market selector to see portfolio health.
          </UnavailableNote>
          <CtaButton onClick={() => navigateTo({ tab: 'portfolio' })}>Build portfolio</CtaButton>
        </div>
      ) : data.positionsLoading || data.historyLoading ? (
        <div className="mt-4 flex flex-1 flex-col justify-center gap-3">
          <div className="h-28 animate-pulse rounded-xl bg-white/[0.03]" />
          <p className="text-[11px] text-muted-foreground">
            {data.positionsLoading ? 'Loading live position values…' : 'Loading trend history…'}
          </p>
        </div>
      ) : (
        <>
          <div className="mt-4 flex items-center gap-4">
            <HealthRing score={data.health.score} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{data.health.label}</span>
                <Pill tone={data.health.score == null ? 'unavailable' : data.health.score >= 70 ? 'bullish' : data.health.score >= 55 ? 'neutral' : 'bearish'}>
                  trend score
                </Pill>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                {data.health.coveragePct.toFixed(0)}% of book value has trend history.
                {data.health.penalty > 0 ? ` Concentration penalty ${data.health.penalty.toFixed(1)} pts.` : ''}
                {data.fxMissingCount > 0 ? ` ${data.fxMissingCount} non-USD holding${data.fxMissingCount === 1 ? '' : 's'} use an FX estimate.` : ''}
              </p>
              <div className="mt-3 space-y-1.5">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="inline-flex items-center gap-1.5 text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Uptrend</span>
                  <span className="tabular-nums text-foreground/80">{formatPct(mix.uptrend)}</span>
                </div>
                <div className="flex items-center justify-between text-[10px]">
                  <span className="inline-flex items-center gap-1.5 text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-zinc-300" />Weak uptrend</span>
                  <span className="tabular-nums text-foreground/80">{formatPct(mix.weakUptrend)}</span>
                </div>
                <div className="flex items-center justify-between text-[10px]">
                  <span className="inline-flex items-center gap-1.5 text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-rose-400" />Downtrend</span>
                  <span className="tabular-nums text-foreground/80">{formatPct(mix.downtrend)}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="mt-4">
            <SplitBar
              segments={[
                { name: 'Uptrend', value: mix.uptrend, color: '#34d399' },
                { name: 'Weak uptrend', value: mix.weakUptrend, color: '#e5e7eb' },
                { name: 'Downtrend', value: mix.downtrend, color: '#fb7185' },
                { name: 'Unknown', value: mix.unknown, color: '#475569' },
              ]}
            />
            <p className="mt-3 border-t border-white/5 pt-3 text-[11px] leading-relaxed text-muted-foreground">
              <span className="text-[9px] font-medium uppercase tracking-[0.14em] text-white/45">Key takeaway · </span>
              {takeaway}
            </p>
          </div>
        </>
      )}
    </HomeCard>
  );
}

export function LeadershipCard({ data }: { data: HomeData }) {
  const leading = data.leading;
  const isGlobal = data.market === 'GLOBAL';
  return (
    <HomeCard className="md:col-span-1 lg:col-span-4">
      <CardTitle
        eyebrow={isGlobal ? 'Leading market' : 'Leading sector'}
        right={<Pill tone={leading ? toneForChange(leading.relative) : 'unavailable'}>{isGlobal ? 'relative strength' : 'vs benchmark'}</Pill>}
      />
      {!leading ? (
        <UnavailableNote className="mt-4">
          Sector and market leadership is unavailable for {data.marketLabel}. The heatmap has no priced instruments right now.
        </UnavailableNote>
      ) : (
        <>
          <div className="mt-4 flex items-start gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/[0.04] text-white/70">
              {isGlobal ? <Globe size={20} /> : <Layers size={20} />}
            </div>
            <div className="min-w-0">
              <h3 className="truncate text-xl font-semibold tracking-tight text-foreground">{leading.name}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
                <ChangeText value={leading.change} />
                <span className="text-muted-foreground/60">vs {formatSignedPct(data.marketChange)} {isGlobal ? 'average' : 'benchmark'}</span>
              </div>
              <p className="mt-1 text-[10px] text-muted-foreground/70">
                {isGlobal ? 'Top relative strength across tracked markets.' : 'Top relative strength across market sectors.'}
              </p>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2">
            <StatTile label={isGlobal ? 'Markets advancing' : 'Sectors advancing'} value={`${data.breadth.advancing}/${data.breadth.tracked}`} sub="latest session" />
            <StatTile label="Beating benchmark" value={`${data.breadth.beating}/${data.breadth.tracked}`} sub="relative strength" />
          </div>

          <div className="mt-4 space-y-1.5">
            {data.signals.slice(0, 4).map((signal, index) => (
              <div key={signal.name} className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-1.5">
                <span className="w-3 shrink-0 text-[9px] tabular-nums text-muted-foreground/50">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-foreground/85">{signal.name}</span>
                {signal.topSymbol && (
                  <SymbolChip symbol={signal.topSymbol} onClick={() => openChart(signal.topSymbol!)} />
                )}
                <span className={cn('w-14 shrink-0 text-right text-[10px] tabular-nums', TONE_TEXT[toneForChange(signal.change)])}>
                  {formatSignedPct(signal.change)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </HomeCard>
  );
}

export function RegimeCard({ data }: { data: HomeData }) {
  const regime = data.regime;
  const available = regime?.coreAvailable === true;
  return (
    <HomeCard className="md:col-span-2 lg:col-span-8">
      <CardTitle
        eyebrow="Market regime"
        title={data.regime?.label ?? 'Unavailable'}
        right={(
          <div className="flex items-center gap-2">
            {data.benchmark && <span className="hidden text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50 sm:inline">{data.benchmark.label}</span>}
            <Pill tone={data.regimeTone}>{TONE_LABEL[data.regimeTone]}</Pill>
          </div>
        )}
      />
      {!available ? (
        <div className="mt-4">
          <UnavailableNote>
            The regime read is unavailable because JDDS has no fresh price-and-breadth input for {data.marketLabel}. This is never shown as a neutral reading.
          </UnavailableNote>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-end justify-between gap-2">
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-semibold tabular-nums text-foreground">
              {regime?.score == null ? '—' : regime.score.toFixed(2)}
            </span>
            <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/60">
              score · {regime ? Math.round(regime.confidence * 100) : 0}% confidence
            </span>
          </div>
          <span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">
            {regime?.asOf ? `as of ${formatAge(regime.asOf)}` : 'timestamp unavailable'}
          </span>
        </div>
      )}

      <div className="mt-3">
        {data.benchmark ? (
          <WeatherLine closes={data.benchmark.closes} dates={data.benchmark.dates} stale={data.benchmark.stale} />
        ) : (
          <div className="flex h-40 items-center justify-center rounded-xl border border-white/5 bg-white/[0.02] text-[10px] uppercase tracking-[0.14em] text-muted-foreground/50">
            benchmark history unavailable
          </div>
        )}
      </div>

      {available && regime && (
        <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-2.5 border-t border-white/5 pt-3 sm:grid-cols-2">
          {regime.components.map((component) => (
            <ComponentMeter
              key={component.id}
              label={component.label}
              score={component.score}
              detail={component.detail}
              available={component.available}
              stale={component.stale}
            />
          ))}
        </div>
      )}
    </HomeCard>
  );
}

export function AttentionCard({ data }: { data: HomeData }) {
  const buckets = [
    { name: 'Best aligned', rows: data.best, tone: 'bullish' as const, icon: TrendingUp },
    { name: 'Stable holdings', rows: data.stable, tone: 'neutral' as const, icon: Target },
    { name: 'Review candidates', rows: data.review, tone: 'bearish' as const, icon: TrendingDown },
  ];
  return (
    <HomeCard className="md:col-span-2 lg:col-span-6">
      <CardTitle
        eyebrow="What needs attention"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">trend classified</span>}
      />
      {data.holdingsCount === 0 ? (
        <UnavailableNote className="mt-4">
          No open holdings in {data.marketLabel}. Add positions to classify the book into aligned, stable and review buckets.
        </UnavailableNote>
      ) : data.historyLoading ? (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-4 text-[11px] text-muted-foreground">
          <span className="h-2 w-2 animate-pulse rounded-full bg-zinc-300" />
          Classifying the book into trend buckets…
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {buckets.map((bucket) => {
            const Icon = bucket.icon;
            return (
              <div key={bucket.name} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.1em] text-muted-foreground">
                    <Icon size={12} className={TONE_TEXT[bucket.tone]} />
                    {bucket.name}
                  </span>
                  <span className={cn('text-sm font-semibold tabular-nums', TONE_TEXT[bucket.tone])}>{bucket.rows.length}</span>
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1">
                  {bucket.rows.slice(0, 6).map((holding) => (
                    <SymbolChip key={holding.symbol} symbol={holding.symbol} tone={bucket.tone} onClick={() => openChart(holding.symbol)} />
                  ))}
                  {bucket.rows.length === 0 && <span className="text-[10px] text-muted-foreground/50">None</span>}
                  {bucket.rows.length > 6 && <span className="text-[10px] text-muted-foreground/50">+{bucket.rows.length - 6}</span>}
                </div>
                {bucket.rows[0] && !data.positionsLoading && (
                  <p className="mt-2 truncate text-[9px] text-muted-foreground/60">
                    Top weight: {bucket.rows[0].symbol} · {formatPct(bucket.rows[0].weightPct)}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
      {data.holdingsCount > 0 && (
        <p className="mt-3 text-[9px] uppercase tracking-[0.12em] text-muted-foreground/45">
          Click a symbol to open its chart
        </p>
      )}
    </HomeCard>
  );
}

export function PortfolioWatchCard({ data }: { data: HomeData }) {
  return (
    <HomeCard className="md:col-span-1 lg:col-span-3">
      <CardTitle eyebrow="Portfolio watch" right={<EyeBadge />} />
      {data.review.length === 0 ? (
        <div className="flex flex-1 flex-col items-start justify-center gap-3 py-4">
          <div>
            <h3 className="text-base font-medium text-foreground">No holdings need review</h3>
            <p className="mt-1 text-[11px] text-muted-foreground">Trend structure is clear across the book.</p>
          </div>
          <CtaButton onClick={() => navigateTo({ tab: 'portfolio' })}>View portfolio</CtaButton>
        </div>
      ) : (
        <>
          <div className="mt-3 space-y-1.5">
            {data.review.slice(0, 3).map((holding) => (
              <button
                key={holding.symbol}
                type="button"
                onClick={() => openChart(holding.symbol)}
                className="flex w-full items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-2 text-left transition-colors hover:border-rose-400/20"
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-[11px] font-medium text-foreground">{holding.symbol}</span>
                  <span className="block truncate text-[9px] text-muted-foreground/70">{holding.name}</span>
                </span>
                <span className="text-right">
                  <ChangeText value={holding.changePercent} className="text-[10px]" />
                  {!data.positionsLoading && (
                    <span className="mt-0.5 block text-[9px] tabular-nums text-muted-foreground/60">{formatPct(holding.weightPct)}</span>
                  )}
                </span>
              </button>
            ))}
          </div>
          <div className="mt-auto pt-3">
            <CtaButton onClick={() => navigateTo({ tab: 'portfolio' })}>Review portfolio</CtaButton>
          </div>
        </>
      )}
    </HomeCard>
  );
}

function EyeBadge() {
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/15 bg-white/[0.04] text-white/70">
      <ScanEye size={15} />
    </span>
  );
}

export function WatchlistRadarCard({ data }: { data: HomeData }) {
  return (
    <HomeCard className="md:col-span-1 lg:col-span-3">
      <CardTitle eyebrow="Watchlist radar" right={<StarBadge />} />
      {data.radar.length === 0 ? (
        <div className="flex flex-1 flex-col items-start justify-center gap-3 py-4">
          <div>
            <h3 className="text-base font-medium text-foreground">No watchlist setups</h3>
            <p className="mt-1 text-[11px] text-muted-foreground">Add saved names to track unheld movers.</p>
          </div>
          <CtaButton onClick={() => navigateTo({ tab: 'portfolio' })}>Add symbols</CtaButton>
        </div>
      ) : (
        <>
          <div className="mt-3 space-y-1.5">
            {data.radar.slice(0, 3).map((row) => (
              <button
                key={row.symbol}
                type="button"
                onClick={() => openChart(row.symbol)}
                className="flex w-full items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-2 text-left transition-colors hover:border-white/20"
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-[11px] font-medium text-foreground">{row.symbol}</span>
                  <span className="block truncate text-[9px] text-muted-foreground/70">{row.name}</span>
                </span>
                <span className="text-right">
                  <span className="block text-[10px] tabular-nums text-foreground/80">{formatPrice(row.price, row.currency)}</span>
                  <ChangeText value={row.changePercent} className="text-[9px]" digits={2} />
                </span>
              </button>
            ))}
          </div>
          <p className="mt-auto pt-3 text-[9px] uppercase tracking-[0.12em] text-muted-foreground/45">
            Unheld names · latest session
          </p>
        </>
      )}
    </HomeCard>
  );
}

function StarBadge() {
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/15 bg-white/[0.04] text-white/70">
      <Star size={15} />
    </span>
  );
}

export function ConcentrationCard({ data }: { data: HomeData }) {
  const concentration = data.concentration;
  return (
    <HomeCard className="md:col-span-1 lg:col-span-4">
      <CardTitle eyebrow="Portfolio concentration" right={<Layers size={14} className="text-white/50" />} />
      {data.holdingsCount === 0 || (data.positionsLoading && concentration.sectorCount === 0) ? (
        <UnavailableNote className="mt-4">
          {data.positionsLoading
            ? 'Loading sector concentration while live prices arrive…'
            : `Sector concentration is unavailable because the book has no classified holdings in ${data.marketLabel}.`}
        </UnavailableNote>
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
        <p className="mt-auto border-t border-white/5 pt-3 text-[10px] leading-relaxed text-muted-foreground/70">
          {concentration.diversified
            ? `Diversified across ${concentration.sectorCount} sectors.`
            : `Top exposure: ${concentration.topSector ?? '—'} at ${formatPct(concentration.topSharePct)}.`}
        </p>
      )}
    </HomeCard>
  );
}

export function UniverseCard({ data }: { data: HomeData }) {
  const global = data.market === 'GLOBAL';
  return (
    <HomeCard accent className="md:col-span-1 lg:col-span-4">
      <CardTitle eyebrow="Full market universe" right={<Globe size={14} className="text-white/50" />} />
      <div className="mt-4">
        <h3 className="max-w-[16rem] text-xl font-semibold leading-tight tracking-tight text-foreground">
          Explore. Filter. Rank. Decide.
        </h3>
        <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
          Screen the JDDS universe with Eclipse&apos;s market tools, then take the strongest setup to the chart.
        </p>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2">
        <StatTile label={global ? 'Live markets' : 'Priced names'} value={global ? data.universe.markets : data.universe.instruments} />
        <StatTile label={global ? 'Market leaders' : 'Sectors'} value={global ? data.universe.instruments : data.universe.tracked} />
        <StatTile
          label="Advancing"
          value={data.universe.advancing}
          tone={data.universe.advancing > data.universe.tracked / 2 ? 'bullish' : 'neutral'}
        />
      </div>
      <div className="relative mt-4 h-16 overflow-hidden rounded-xl border border-white/5 bg-gradient-to-br from-white/[0.05] to-transparent">
        <svg viewBox="0 0 160 60" className="absolute inset-0 h-full w-full" aria-hidden>
          <defs>
            <linearGradient id="universe-bars" x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%" stopColor="#f8fafc" stopOpacity="0.05" />
              <stop offset="100%" stopColor="#f8fafc" stopOpacity="0.6" />
            </linearGradient>
          </defs>
          {[12, 26, 40, 54, 68, 82, 96, 110, 124, 138].map((x, index) => {
            const height = 10 + ((index * 17) % 34);
            return <rect key={x} x={x} y={56 - height} width="5" height={height} rx="1.5" fill="url(#universe-bars)" />;
          })}
          <path d="M4 48 C30 44, 42 30, 62 34 S96 18, 116 22 S140 10, 156 8" fill="none" stroke="#e5e7eb" strokeOpacity="0.55" strokeWidth="1.2" />
        </svg>
        <div className="absolute inset-0 bg-gradient-to-r from-black/20 via-transparent to-black/20" />
      </div>
      <div className="mt-4 flex items-center gap-2">
        <CtaButton onClick={() => navigateTo({ tab: 'discovery' })}>Open screener</CtaButton>
        <GhostButton onClick={() => navigateTo({ tab: 'heatmap' })}>Open heatmap</GhostButton>
      </div>
    </HomeCard>
  );
}

export function AlertsCard({ data }: { data: HomeData }) {
  return (
    <HomeCard className="md:col-span-1 lg:col-span-4">
      <CardTitle eyebrow="Alerts archive" right={<Bell size={14} className="text-white/50" />} />
      <div className="mt-3 flex items-center gap-4">
        <div>
          <p className="text-lg font-semibold tabular-nums text-foreground">{data.activeAlerts}</p>
          <p className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">active watches</p>
        </div>
        <div>
          <p className="text-lg font-semibold tabular-nums text-foreground">{data.alerts.length}</p>
          <p className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">total watches</p>
        </div>
      </div>
      <div className="mt-3 flex-1 space-y-1.5">
        {data.recentAlerts.length === 0 ? (
          <p className="rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-2 text-[10px] text-muted-foreground">
            No alerts have fired yet. Create a watch to start the archive.
          </p>
        ) : (
          data.recentAlerts.map((alert) => (
            <div key={alert.id} className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-1.5">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[11px] text-foreground/85">{alert.name}</span>
                <span className="block truncate text-[9px] text-muted-foreground/60">{alert.symbols.join(', ')}</span>
              </span>
              <span className="shrink-0 text-right text-[9px] text-muted-foreground/60">
                {alert.lastFiredAt ? formatAge(alert.lastFiredAt) : alert.status}
              </span>
            </div>
          ))
        )}
      </div>
      <div className="mt-3">
        <CtaButton onClick={() => navigateTo({ tab: 'alerts' })}>View alerts</CtaButton>
      </div>
    </HomeCard>
  );
}

export function MarketTapeStrip({ data }: { data: HomeData }) {
  const top = data.signals.slice(0, 5);
  if (top.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="inline-flex items-center gap-1.5 text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">
        <Sparkles size={11} className="text-white/50" /> Tape
      </span>
      {top.map((signal) => (
        <span key={signal.name} className="inline-flex items-center gap-1.5 rounded-full border border-white/5 bg-white/[0.02] px-2 py-0.5 text-[9px] text-muted-foreground">
          <span className="max-w-[8rem] truncate">{signal.name}</span>
          <span className={cn('tabular-nums', TONE_TEXT[toneForChange(signal.change)])}>{formatSignedPct(signal.change)}</span>
        </span>
      ))}
    </div>
  );
}

export function DashboardFooter({ data }: { data: HomeData }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-1 text-[9px] uppercase tracking-[0.12em] text-muted-foreground/40">
      <span className="inline-flex items-center gap-1.5">
        <ChartLine size={11} />
        {data.marketLabel} · {data.trackedLabel === 'markets' ? 'market breadth' : 'sector breadth'}
      </span>
      <span className="inline-flex items-center gap-3">
        <span className="inline-flex items-center gap-1"><Briefcase size={10} />{data.holdingsCount} holdings</span>
        <span>{data.fundsCount} funds</span>
        <span>JDDS · real data</span>
      </span>
    </div>
  );
}
