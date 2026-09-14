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
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTopic } from '@/lib/workspace/data-hub';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';

const UP = 'text-emerald-400';
const DOWN = 'text-rose-400';
const tone = (n: number) => (n > 0 ? UP : n < 0 ? DOWN : 'text-muted-foreground');
const fmt = (n?: number | null, d = 2) => (n == null || !Number.isFinite(n) ? '—' : n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));

interface IndexRow { name: string; symbol: string; price: number; change: number; changePercent: number; }
interface CommodityRow { symbol: string; name: string; price: number; changePct: number; found: boolean; }
interface ForexRow { symbol: string; name: string; price: number; changePct: number; found: boolean; }
interface OverviewGroup { id: string; country: string; name?: string; stocks: { symbol: string; name: string; price: number; changePct: number }[]; }

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 block">
      {children}
    </span>
  );
}

// ── Fear & Greed ─────────────────────────────────────────────────────────────
function useFearGreed() {
  const indices = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const overview = useTopic<{ groups: OverviewGroup[] }>('market:overview');
  const rows = indices.data?.indices ?? [];
  const stocks = overview.data?.groups?.find(g => g.id === 'US')?.stocks ?? [];
  const adv = stocks.filter(s => s.changePct > 0).length;
  const dec = stocks.filter(s => s.changePct < 0).length;
  const total = adv + dec || 1;
  const breadth = (adv / total) * 100;
  const momentum = rows.length ? (rows.reduce((a, i) => a + (i.changePercent > 0 ? 1 : 0), 0) / rows.length) * 100 : 50;
  return Math.round(Math.min(100, Math.max(0, breadth * 0.6 + momentum * 0.4)));
}

function FearGreedWidget() {
  const fearGreed = useFearGreed();
  return (
    <div className="flex h-full flex-col p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          <Gauge size={11} className="text-primary" /> Fear &amp; Greed
        </span>
        <span className="font-mono text-sm font-bold text-foreground">{fearGreed}</span>
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
function MarketBreadthWidget() {
  const overview = useTopic<{ groups: OverviewGroup[] }>('market:overview');
  const stocks = overview.data?.groups?.find(g => g.id === 'US')?.stocks ?? [];
  const adv = stocks.filter(s => s.changePct > 0).length;
  const dec = stocks.filter(s => s.changePct < 0).length;
  const rows = [
    { label: 'NYSE', adv, dec },
    { label: 'NASDAQ', adv, dec },
    { label: 'S&P 500', adv, dec },
  ];
  return (
    <div className="flex h-full flex-col p-3">
      <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
        <Activity size={11} className="text-primary" /> Market Breadth
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
function TopMoversPanelWidget() {
  const overview = useTopic<{ groups: OverviewGroup[] }>('market:overview');
  const stocks = overview.data?.groups?.find(g => g.id === 'US')?.stocks ?? [];
  const gainers = [...stocks].filter(s => s.changePct > 0).sort((a, b) => b.changePct - a.changePct).slice(0, 5);
  const losers = [...stocks].filter(s => s.changePct < 0).sort((a, b) => a.changePct - b.changePct).slice(0, 5);
  return (
    <div className="flex h-full flex-col p-3">
      <SectionTitle>Top Movers</SectionTitle>
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
function GlobalSnapshotWidget() {
  const indices = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const commodities = useTopic<{ commodities: CommodityRow[] }>('market:commodities');
  const forex = useTopic<{ pairs: ForexRow[] }>('market:forex');
  const idx = indices.data?.indices ?? [];
  const com = commodities.data?.commodities ?? [];
  const fx = forex.data?.pairs ?? [];
  const find = (name: string) => idx.find(i => i.name.toLowerCase().includes(name.toLowerCase()));
  const gold = com.find(c => c.name.toLowerCase().includes('gold'));
  const oil = com.find(c => c.name.toLowerCase().includes('crude'));
  const dxy = fx.find(f => f.symbol === 'DXY=X');
  const rows = [
    { label: 'VIX', value: find('vix')?.price, change: find('vix')?.changePercent },
    { label: 'US 10Y', value: find('10y')?.price, change: find('10y')?.changePercent },
    { label: 'DXY', value: dxy?.price, change: dxy?.changePct },
    { label: 'Gold', value: gold?.price, change: gold?.changePct },
    { label: 'Oil WTI', value: oil?.price, change: oil?.changePct },
    { label: 'BTC', value: find('bitcoin')?.price, change: find('bitcoin')?.changePercent },
  ];
  return (
    <div className="flex h-full flex-col p-3">
      <SectionTitle>Global Snapshot</SectionTitle>
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

function MarketHoursWidget() {
  return (
    <div className="flex h-full flex-col p-3">
      <SectionTitle>Market Hours</SectionTitle>
      <div className="flex flex-col gap-1">
        {EXCHANGES.map(ex => {
          const st = marketStatus(ex.tz, ex.open, ex.close);
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

// ── Live market widgets (self-contained) ─────────────────────────────────────
function LiveIndicesWidget() {
  const t = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const rows = t.data?.indices ?? [];
  return (
    <div className="flex h-full flex-col p-3">
      <SectionTitle>Market Indices</SectionTitle>
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
      <SectionTitle>Forex</SectionTitle>
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
  const t = useTopic<{ indices: IndexRow[] }>('market:indices:CRYPTO');
  const rows = t.data?.indices ?? [];
  return (
    <div className="flex h-full flex-col p-3">
      <SectionTitle>Crypto</SectionTitle>
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
      <SectionTitle>Commodities</SectionTitle>
      <div className="flex flex-1 flex-col gap-1">
        {rows.slice(0, 8).map(c => (
          <div key={c.symbol} className="flex items-center justify-between text-[10px] py-0.5">
            <span className="font-mono font-bold text-foreground">{c.name}</span>
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

const ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  gauge: Gauge, activity: Activity, trending: TrendingUp, globe: GlobeIcon,
  'line-chart': LineChart, table: Table2, newspaper: Newspaper, landmark: Landmark,
  flame: Flame, coins: Coins, percent: Percent, 'arrow-up-down': ArrowUpDown,
  candlestick: CandlestickChart,
};

export function marketPanelIcon(name: string): React.ComponentType<{ size?: number; className?: string }> | undefined {
  return ICONS[name];
}

export const MARKET_RAIL_WIDGETS: WidgetDefinition[] = [
  { id: 'mp-fear-greed', category: 'markets', label: 'Fear & Greed', desc: 'Composite sentiment gauge.', icon: 'gauge', sizes: ['small', 'medium'], render: () => <FearGreedWidget /> },
  { id: 'mp-breadth', category: 'markets', label: 'Market Breadth', desc: 'Advancers vs decliners.', icon: 'activity', sizes: ['small', 'medium'], render: () => <MarketBreadthWidget /> },
  { id: 'mp-movers', category: 'markets', label: 'Top Movers', desc: 'Biggest gainers and losers.', icon: 'trending', sizes: ['small', 'medium'], render: () => <TopMoversPanelWidget /> },
  { id: 'mp-snapshot', category: 'macro', label: 'Global Snapshot', desc: 'VIX, US 10Y, DXY, Gold, Oil, BTC.', icon: 'globe', sizes: ['small', 'medium'], render: () => <GlobalSnapshotWidget /> },
  { id: 'mp-hours', category: 'markets', label: 'Market Hours', desc: 'Exchange open/closed status.', icon: 'activity', sizes: ['small', 'medium'], render: () => <MarketHoursWidget /> },
  { id: 'mp-indices', category: 'markets', label: 'Market Indices', desc: 'Major US indices, live.', icon: 'line-chart', sizes: ['small', 'medium'], render: () => <LiveIndicesWidget /> },
  { id: 'mp-forex', category: 'markets', label: 'Forex', desc: 'Major FX pairs, live.', icon: 'arrow-up-down', sizes: ['small', 'medium'], render: () => <LiveForexWidget /> },
  { id: 'mp-crypto', category: 'markets', label: 'Crypto', desc: 'BTC, ETH, SOL and more, live.', icon: 'coins', sizes: ['small', 'medium'], render: () => <LiveCryptoWidget /> },
  { id: 'mp-commodities', category: 'markets', label: 'Commodities', desc: 'Gold, Oil, Gas, Copper, live.', icon: 'flame', sizes: ['small', 'medium'], render: () => <LiveCommoditiesWidget /> },
];
