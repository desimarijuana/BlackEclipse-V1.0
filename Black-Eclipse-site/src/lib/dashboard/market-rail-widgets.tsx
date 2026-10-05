'use client';

// ── Market rail widget catalog ───────────────────────────────────────────────
// The Command Center's default right-hand ("rail") column is built from these
// widgets. They are ordinary WidgetDefinitions in the dashboard catalog, so the
// same Customize button + drag engine arranges them and a card can be dragged
// from the centre into the rail (and back). No separate customization surface.

import React from 'react';
import {
  Activity, CandlestickChart, TrendingUp, Gauge, Globe as GlobeIcon, LineChart,
  Table2, Newspaper, Landmark, Flame, Coins, Percent, ArrowUpDown,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useTopic } from '@/lib/workspace/data-hub';
import { MARKET_SEEDS } from '@/lib/scraper/markets';
import { useMarketIndices, useMarketGroup, marketViewName, MARKET_CONFIG_FIELD, MARKET_FOLLOW } from './market-views';
import { MarketPicker } from '@/components/workspace/market-picker';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WidgetPlacement } from '@/lib/workspace/types';

const UP = 'text-emerald-400';
const DOWN = 'text-rose-400';
const tone = (n: number) => (n > 0 ? UP : n < 0 ? DOWN : 'text-muted-foreground');
const fmt = (n?: number | null, d = 2) => (n == null || !Number.isFinite(n) ? '—' : n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));

interface CommodityRow { symbol: string; name: string; price: number; changePct: number; found: boolean; }
interface ForexRow { symbol: string; name: string; price: number; changePct: number; found: boolean; }

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 block">
      {children}
    </span>
  );
}

/** Header showing which market the widget is currently rendering. */
function MarketChip({ market }: { market: string }) {
  return (
    <span className="font-mono text-[9px] font-bold uppercase tracking-wide text-primary shrink-0">
      {marketViewName(market)}
    </span>
  );
}

type PlacementLike = { config?: Record<string, unknown> } | undefined;

// ── Fear & Greed ─────────────────────────────────────────────────────────────
function useFearGreed(placement?: PlacementLike) {
  const { rows: indexRows } = useMarketIndices(placement);
  const { stocks } = useMarketGroup(placement);
  const rows = indexRows;
  const adv = stocks.filter(s => s.changePct > 0).length;
  const dec = stocks.filter(s => s.changePct < 0).length;
  const total = adv + dec || 1;
  const breadth = (adv / total) * 100;
  const momentum = rows.length ? (rows.reduce((a, i) => a + (i.changePercent > 0 ? 1 : 0), 0) / rows.length) * 100 : 50;
  return Math.round(Math.min(100, Math.max(0, breadth * 0.6 + momentum * 0.4)));
}

function FearGreedWidget({ placement }: { placement?: WidgetPlacement }) {
  const fearGreed = useFearGreed(placement);
  return (
    <div className="flex h-full flex-col p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          <Gauge size={11} className="text-primary" /> Fear &amp; Greed
        </span>
        <span className="flex items-center gap-2">
          <MarketPicker placement={placement} />
          <span className="font-mono text-sm font-bold text-foreground">{fearGreed}</span>
        </span>
      </div>
      <div className="h-2 rounded-full bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-400 overflow-hidden">
        <div className="h-full bg-background/70" style={{ width: `${100 - fearGreed}%`, marginLeft: 'auto' }} />
      </div>
      <div className="mt-1 flex justify-between text-[8px] text-muted-foreground/60">
        <span>Extreme Fear</span><span>Neutral</span><span>Extreme Greed</span>
      </div>
    </div>
  );
}

// ── Market Breadth ───────────────────────────────────────────────────────────
function MarketBreadthWidget({ placement }: { placement?: WidgetPlacement }) {
  const { market, stocks, group } = useMarketGroup(placement);
  const adv = stocks.filter(s => s.changePct > 0).length;
  const dec = stocks.filter(s => s.changePct < 0).length;
  const label = group?.exchange || marketViewName(market);
  const rows = [
    { label, adv, dec },
  ];
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          <Activity size={11} className="text-primary" /> Market Breadth
        </span>
        <MarketPicker placement={placement} />
      </span>
      <div className="flex flex-col gap-1.5">
        {rows.map(m => {
          const total = m.adv + m.dec || 1;
          const advPct = (m.adv / total) * 100;
          return (
            <div key={m.label} className="flex items-center gap-2 text-[10px]">
              <span className="w-14 shrink-0 text-muted-foreground">{m.label}</span>
              <div className="flex flex-1 h-1.5 rounded-full overflow-hidden">
                <div className="bg-emerald-400" style={{ width: `${advPct}%` }} />
                <div className="bg-rose-400" style={{ width: `${100 - advPct}%` }} />
              </div>
              <span className="w-8 text-right font-mono text-emerald-400">{m.adv}</span>
              <span className="w-8 text-right font-mono text-rose-400">{m.dec}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Top Movers ───────────────────────────────────────────────────────────────
function TopMoversPanelWidget({ placement }: { placement?: WidgetPlacement }) {
  const { stocks } = useMarketGroup(placement);
  const gainers = [...stocks].filter(s => s.changePct > 0).sort((a, b) => b.changePct - a.changePct).slice(0, 5);
  const losers = [...stocks].filter(s => s.changePct < 0).sort((a, b) => a.changePct - b.changePct).slice(0, 5);
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>Top Movers</SectionTitle>
        <MarketPicker placement={placement} />
      </span>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <span className="flex items-center gap-1 text-[9px] font-bold text-emerald-400 mb-1"><TrendingUp size={10} /> Gainers</span>
          {gainers.map(s => (
            <div key={s.symbol} className="flex items-center justify-between text-[10px] py-0.5">
              <span className="font-mono font-bold text-foreground">{s.symbol}</span>
              <span className={cn('font-mono', tone(s.changePct))}>{s.changePct > 0 ? '+' : ''}{fmt(s.changePct)}%</span>
            </div>
          ))}
        </div>
        <div>
          <span className="flex items-center gap-1 text-[9px] font-bold text-rose-400 mb-1"><TrendingUp size={10} className="rotate-180" /> Losers</span>
          {losers.map(s => (
            <div key={s.symbol} className="flex items-center justify-between text-[10px] py-0.5">
              <span className="font-mono font-bold text-foreground">{s.symbol}</span>
              <span className={cn('font-mono', tone(s.changePct))}>{s.changePct > 0 ? '+' : ''}{fmt(s.changePct)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Global Snapshot ──────────────────────────────────────────────────────────
function GlobalSnapshotWidget({ placement }: { placement?: WidgetPlacement }) {
  const { market, rows: idx } = useMarketIndices(placement);
  const commodities = useTopic<{ commodities: CommodityRow[] }>('market:commodities');
  const forex = useTopic<{ pairs: ForexRow[] }>('market:forex');
  const com = commodities.data?.commodities ?? [];
  const fx = forex.data?.pairs ?? [];
  const find = (name: string) => idx.find(i => i.name.toLowerCase().includes(name.toLowerCase()));
  const gold = com.find(c => c.name.toLowerCase().includes('gold'));
  const oil = com.find(c => c.name.toLowerCase().includes('crude'));
  const dxy = fx.find(f => f.symbol === 'DXY=X');
  // Lead with the active market's own headline index (its first row), then the
  // cross-asset macro anchors so the panel always reflects the chosen country.
  const headline = idx[0];
  const rows = [
    headline
      ? { label: headline.name, value: headline.price, change: headline.changePercent }
      : { label: marketViewName(market), value: undefined, change: undefined },
    { label: 'VIX', value: find('vix')?.price, change: find('vix')?.changePercent },
    { label: 'US 10Y', value: find('10y')?.price, change: find('10y')?.changePercent },
    { label: 'DXY', value: dxy?.price, change: dxy?.changePct },
    { label: 'Gold', value: gold?.price, change: gold?.changePct },
    { label: 'Oil WTI', value: oil?.price, change: oil?.changePct },
    { label: 'BTC', value: find('bitcoin')?.price, change: find('bitcoin')?.changePercent },
  ];
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>Global Snapshot</SectionTitle>
        <MarketPicker placement={placement} />
      </span>
      <div className="flex flex-col gap-1">
        {rows.map(s => (
          <div key={s.label} className="flex items-center justify-between text-[10px]">
            <span className="text-muted-foreground">{s.label}</span>
            <span className="flex items-center gap-2">
              <span className="font-mono text-foreground">{s.value != null ? s.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}</span>
              {s.change != null && <span className={cn('font-mono w-12 text-right', tone(s.change))}>{s.change > 0 ? '+' : ''}{fmt(s.change)}%</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Market Hours ─────────────────────────────────────────────────────────────
const EXCHANGES = [
  { label: 'NYSE', tz: 'America/New_York', open: 9, close: 16 },
  { label: 'LSE', tz: 'Europe/London', open: 8, close: 16 },
  { label: 'Tokyo', tz: 'Asia/Tokyo', open: 9, close: 15 },
  { label: 'Shanghai', tz: 'Asia/Shanghai', open: 9, close: 15 },
  { label: 'NSE', tz: 'Asia/Kolkata', open: 9, close: 15 },
];

/** Resolve a market's exchange/session row (from the scrape seeds) for display. */
function marketExchange(market: string, label?: string): { label: string; tz: string; open: number; close: number; crypto?: boolean } | null {
  const seed = MARKET_SEEDS.find(s => s.id === market);
  if (!seed && !label) return null;
  return {
    label: seed?.exchange || label || marketViewName(market),
    tz: seed?.timezone ?? EXTRA_TZ[market] ?? 'UTC',
    open: seed?.openHour ?? 9,
    close: seed?.closeHour ?? 17,
    crypto: seed?.isCrypto,
  };
}

const EXTRA_TZ: Record<string, string> = {
  FOREX: 'UTC', COMMODITIES: 'UTC', CN: 'Asia/Shanghai', TW: 'Asia/Taipei',
  HK: 'Asia/Hong_Kong', JP: 'Asia/Tokyo', KR: 'Asia/Seoul', SG: 'Asia/Singapore',
  MY: 'Asia/Kuala_Lumpur', AU: 'Australia/Sydney', UK: 'Europe/London',
  DE: 'Europe/Berlin', FR: 'Europe/Paris', NL: 'Europe/Amsterdam', CA: 'America/Toronto',
  BR: 'America/Sao_Paulo', MX: 'America/Mexico_City', SA: 'Asia/Riyadh', AE: 'Asia/Dubai',
  ZA: 'Africa/Johannesburg', EG: 'Africa/Cairo', NG: 'Africa/Lagos', RU: 'Europe/Moscow',
  TR: 'Europe/Istanbul', ID: 'Asia/Jakarta', TH: 'Asia/Bangkok', VN: 'Asia/Ho_Chi_Minh',
};

function marketStatus(tz: string, openHour: number, closeHour: number): 'open' | 'closed' | 'pre' {
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', hour12: false, weekday: 'short' }).formatToParts(new Date());
    const hour = Number(parts.find(p => p.type === 'hour')?.value ?? NaN);
    const wd = parts.find(p => p.type === 'weekday')?.value ?? '';
    const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const weekday = weekdays.indexOf(wd);
    if (!Number.isFinite(hour) || weekday < 0) return 'open';
    if (weekday === 0 || weekday === 6) return 'closed';
    if (hour >= openHour && hour < closeHour) return 'open';
    if (hour >= openHour - 1 && hour < openHour) return 'pre';
    return 'closed';
  } catch { return 'open'; }
}

function MarketHoursWidget({ placement }: { placement?: WidgetPlacement }) {
  const { market, group } = useMarketGroup(placement);
  // Show the active market's own exchange first (when we know its session).
  const active = marketExchange(market, group?.exchange);
  const list = active && !EXCHANGES.some(ex => ex.label === active.label)
    ? [active, ...EXCHANGES]
    : EXCHANGES;
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>Market Hours</SectionTitle>
        <MarketPicker placement={placement} />
      </span>
      <div className="flex flex-col gap-1">
        {list.map(ex => {
          const st = ('crypto' in ex && ex.crypto) ? 'open' : marketStatus(ex.tz, ex.open, ex.close);
          return (
            <div key={ex.label} className="flex items-center justify-between text-[10px]">
              <span className="text-muted-foreground">{ex.label}</span>
              <span className="flex items-center gap-1.5">
                <span className={cn('h-2 w-2 rounded-full', st === 'open' ? 'bg-emerald-400' : st === 'pre' ? 'bg-amber-400' : 'bg-rose-400')} />
                <span className={cn('font-mono capitalize', st === 'open' ? 'text-emerald-400' : st === 'pre' ? 'text-amber-400' : 'text-rose-400')}>{st}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Live market widgets (self-contained, follow the active market tab) ───────
function LiveIndicesWidget({ placement }: { placement?: WidgetPlacement }) {
  const { rows } = useMarketIndices(placement);
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>Market Indices</SectionTitle>
        <MarketPicker placement={placement} />
      </span>
      <div className="flex flex-1 flex-col gap-1">
        {rows.slice(0, 8).map(i => (
          <div key={i.symbol} className="flex items-center justify-between text-[10px] py-0.5">
            <span className="font-mono font-bold text-foreground">{i.name}</span>
            <span className="flex items-center gap-2">
              <span className="font-mono text-foreground">{fmt(i.price)}</span>
              <span className={cn('font-mono w-12 text-right', tone(i.changePercent))}>{i.changePercent > 0 ? '+' : ''}{fmt(i.changePercent)}%</span>
            </span>
          </div>
        ))}
        {rows.length === 0 && <p className="text-[10px] text-muted-foreground/60 italic py-4 text-center">Loading indices…</p>}
      </div>
    </div>
  );
}

function LiveForexWidget() {
  const t = useTopic<{ pairs: ForexRow[] }>('market:forex');
  const rows = t.data?.pairs ?? [];
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>Forex</SectionTitle>
        <MarketChip market="FOREX" />
      </span>
      <div className="flex flex-1 flex-col gap-1">
        {rows.slice(0, 8).map(p => (
          <div key={p.symbol} className="flex items-center justify-between text-[10px] py-0.5">
            <span className="font-mono font-bold text-foreground">{p.symbol.replace('=X', '')}</span>
            <span className="flex items-center gap-2">
              <span className="font-mono text-foreground">{fmt(p.price, 4)}</span>
              <span className={cn('font-mono w-12 text-right', tone(p.changePct))}>{p.changePct > 0 ? '+' : ''}{fmt(p.changePct)}%</span>
            </span>
          </div>
        ))}
        {rows.length === 0 && <p className="text-[10px] text-muted-foreground/60 italic py-4 text-center">Loading forex…</p>}
      </div>
    </div>
  );
}

function LiveCryptoWidget() {
  // Always the crypto market feed, regardless of the active country tab.
  const { rows } = useMarketIndices({ config: { market: 'CRYPTO' } });
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>Crypto</SectionTitle>
        <MarketChip market="CRYPTO" />
      </span>
      <div className="flex flex-1 flex-col gap-1">
        {rows.slice(0, 8).map(i => (
          <div key={i.symbol} className="flex items-center justify-between text-[10px] py-0.5">
            <span className="font-mono font-bold text-foreground">{i.name}</span>
            <span className="flex items-center gap-2">
              <span className="font-mono text-foreground">{fmt(i.price)}</span>
              <span className={cn('font-mono w-12 text-right', tone(i.changePercent))}>{i.changePercent > 0 ? '+' : ''}{fmt(i.changePercent)}%</span>
            </span>
          </div>
        ))}
        {rows.length === 0 && <p className="text-[10px] text-muted-foreground/60 italic py-4 text-center">Loading crypto…</p>}
      </div>
    </div>
  );
}

function LiveCommoditiesWidget() {
  const t = useTopic<{ commodities: CommodityRow[] }>('market:commodities');
  const rows = t.data?.commodities ?? [];
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>Commodities</SectionTitle>
        <MarketChip market="COMMODITIES" />
      </span>
      <div className="flex flex-1 flex-col gap-1">
        {rows.slice(0, 8).map(c => (
          <div key={c.symbol} className="flex items-center justify-between text-[10px] py-0.5">
            <span className="font-mono font-bold text-foreground truncate">{c.name}</span>
            <span className="flex items-center gap-2">
              <span className="font-mono text-foreground">{fmt(c.price)}</span>
              <span className={cn('font-mono w-12 text-right', tone(c.changePct))}>{c.changePct > 0 ? '+' : ''}{fmt(c.changePct)}%</span>
            </span>
          </div>
        ))}
        {rows.length === 0 && <p className="text-[10px] text-muted-foreground/60 italic py-4 text-center">Loading commodities…</p>}
      </div>
    </div>
  );
}

// ── Country Watch — the active market's own top constituents ─────────────────
function CountryWatchWidget({ placement }: { placement?: WidgetPlacement }) {
  const { market, stocks, group } = useMarketGroup(placement);
  return (
    <div className="flex h-full flex-col p-3">
      <span className="mb-2 flex items-center justify-between gap-2">
        <SectionTitle>{marketViewName(market)} Top Stocks</SectionTitle>
        <MarketPicker placement={placement} />
      </span>
      {stocks.length === 0 ? (
        <p className="py-4 text-center text-[10px] italic text-muted-foreground/60">
          No priced constituents for {marketViewName(market)} in JDDS yet.
        </p>
      ) : (
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto scrollbar-hide">
          {stocks.slice(0, 8).map(s => (
            <div key={s.symbol} className="flex items-center justify-between gap-2 text-[10px] py-0.5">
              <span className="font-mono font-bold text-foreground truncate">{s.symbol}</span>
              <span className="flex items-center gap-2 shrink-0">
                <span className="font-mono text-foreground">{fmt(s.price)}</span>
                <span className={cn('w-12 text-right font-mono', tone(s.changePct))}>
                  {s.changePct > 0 ? '+' : ''}{fmt(s.changePct)}%
                </span>
              </span>
            </div>
          ))}
          {group?.indexName && (
            <p className="mt-1 text-[9px] uppercase tracking-widest text-muted-foreground/60">{group.indexName}</p>
          )}
        </div>
      )}
    </div>
  );
}

const ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  gauge: Gauge, activity: Activity, trending: TrendingUp, globe: GlobeIcon,
  'line-chart': LineChart, table: Table2, newspaper: Newspaper, landmark: Landmark,
  flame: Flame, coins: Coins, percent: Percent, 'arrow-up-down': ArrowUpDown,
  candlestick: CandlestickChart,
};

export function marketPanelIcon(name: string): React.ComponentType<{ size?: number; className?: string }> | undefined {
  return ICONS[name];
}

// Every rail widget is market-aware and exposes the shared Market config field
// so the user can pin it to any market (or leave it following the active tab).
// Forex / Commodities / Crypto feed widgets are naturally locked to their own
// asset class, so they omit the field.
function railDef(
  id: string,
  category: WidgetDefinition['category'],
  label: string,
  desc: string,
  icon: string,
  sizes: WidgetDefinition['sizes'],
  render: (p: WidgetPlacement) => React.ReactNode,
  configurable = true,
): WidgetDefinition {
  return {
    id, category, label, desc, icon, sizes,
    configFields: configurable ? [MARKET_CONFIG_FIELD] : undefined,
    defaultConfig: configurable ? { market: MARKET_FOLLOW } : undefined,
    render: (placement) => render(placement),
  };
}

export const MARKET_RAIL_WIDGETS: WidgetDefinition[] = [
  railDef('mp-fear-greed', 'markets', 'Fear & Greed', 'Composite sentiment gauge.', 'gauge', ['small', 'medium'], (p) => <FearGreedWidget placement={p} />),
  railDef('mp-breadth', 'markets', 'Market Breadth', 'Advancers vs decliners.', 'activity', ['small', 'medium'], (p) => <MarketBreadthWidget placement={p} />),
  railDef('mp-movers', 'markets', 'Top Movers', 'Biggest gainers and losers.', 'trending', ['small', 'medium'], (p) => <TopMoversPanelWidget placement={p} />),
  railDef('mp-snapshot', 'macro', 'Global Snapshot', 'Headline index, VIX, 10Y, DXY, Gold, Oil, BTC.', 'globe', ['small', 'medium'], (p) => <GlobalSnapshotWidget placement={p} />),
  railDef('mp-hours', 'markets', 'Market Hours', 'Exchange open/closed status.', 'activity', ['small', 'medium'], (p) => <MarketHoursWidget placement={p} />),
  railDef('mp-indices', 'markets', 'Market Indices', 'Headline indices for the chosen market.', 'line-chart', ['small', 'medium'], (p) => <LiveIndicesWidget placement={p} />),
  railDef('mp-forex', 'markets', 'Forex', 'Major FX pairs, live.', 'arrow-up-down', ['small', 'medium'], () => <LiveForexWidget />, false),
  railDef('mp-crypto', 'markets', 'Crypto', 'BTC, ETH, SOL and more, live.', 'coins', ['small', 'medium'], () => <LiveCryptoWidget />, false),
  railDef('mp-commodities', 'markets', 'Commodities', 'Gold, Oil, Gas, Copper, live.', 'flame', ['small', 'medium'], () => <LiveCommoditiesWidget />, false),
  railDef('mp-country-watch', 'markets', 'Country Watch', "The chosen market's own top constituents.", 'table', ['medium', 'large'], (p) => <CountryWatchWidget placement={p} />),
];
