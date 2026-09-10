'use client';

// ── Dashboard widget renderers ───────────────────────────────────────────────
// Real data widgets for the Command Center catalog. Each consumes DataHub
// topics and reports null/empty where data is missing — never fabricates.
// Widgets needing external/broker integrations (not yet wired) render a clear
// UNAVAILABLE state instead of fake data.

import React, { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useTopic } from '@/lib/workspace/data-hub';

const UP = 'text-emerald-400';
const DOWN = 'text-rose-400';
const tone = (n: number) => (n > 0 ? UP : n < 0 ? DOWN : 'text-muted-foreground');
const fmt = (n?: number | null, d = 2) => (n == null || !Number.isFinite(n) ? '—' : n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));

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

function Unavailable({ label }: { label: string }) {
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title={label} />
      <div className="flex flex-1 items-center justify-center text-center">
        <p className="text-xs text-amber-400/80 italic max-w-[24ch]">UNAVAILABLE — data source not connected yet.</p>
      </div>
    </div>
  );
}

/** Tiny inline SVG sparkline — up green, down red (like a market watchlist). */
export function Sparkline({ points, width = 96, height = 24 }: { points: number[]; width?: number; height?: number }) {
  const clean = points.filter(p => Number.isFinite(p) && p > 0);
  if (clean.length < 2) return <span className="inline-block" style={{ width, height }} />;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const range = max - min || 1;
  const step = width / (clean.length - 1);
  const path = clean.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(height - ((p - min) / range) * height).toFixed(1)}`).join(' ');
  const up = clean[clean.length - 1] >= clean[0];
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden>
      <path d={path} fill="none" stroke={up ? '#34d399' : '#fb7185'} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** Fetches REAL price history for a symbol and renders a sparkline of actual closes. */
const sparkCache = new Map<string, number[]>();
export function RealSparkline({ symbol, market = 'US', width = 96, height = 24 }: { symbol: string; market?: string; width?: number; height?: number }) {
  const key = `${market}:${symbol}`;
  const [points, setPoints] = useState<number[]>(() => sparkCache.get(key) ?? []);
  useEffect(() => {
    if (sparkCache.has(key)) return;
    let cancelled = false;
    fetch(`/api/price-history?symbol=${encodeURIComponent(symbol)}&market=${market}&range=1mo`)
      .then(r => r.json())
      .then((d: { points?: number[] }) => {
        if (cancelled) return;
        if (d.points && d.points.length) { sparkCache.set(key, d.points); setPoints(d.points); }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [key, symbol, market]);
  return <Sparkline points={points} width={width} height={height} />;
}

// ── Data shapes ──────────────────────────────────────────────────────────────
interface IndexRow { name: string; symbol: string; price: number; change: number; changePercent: number; sparkline?: number[]; }
interface CommodityRow { symbol: string; name: string; price: number; changePct: number; found: boolean; }
interface ForexRow { symbol: string; name: string; price: number; changePct: number; found: boolean; }
interface OverviewGroup { id: string; country: string; name?: string; stocks: { symbol: string; name: string; price: number; changePct: number }[]; }
interface NewsRow { id: string; source: string; ticker?: string | null; headline: string; summary?: string | null; sentiment: string; timestamp: string; category?: string | null; }
interface CalendarEvent { id: string; date: string; country: string; title: string; importance: 'high' | 'medium' | 'low'; actual: string | null; forecast: string | null; previous: string | null; }
interface QuoteRow { symbol: string; name: string; price: number; changePercent: number; currency: string; found: boolean; }

// ── Markets ──────────────────────────────────────────────────────────────────

export function MarketIndicesWidget() {
  const t = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const rows = t.data?.indices ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Market Indices" hint="US" />
      {rows.length === 0 ? <EmptyNote>Loading indices…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1">
          {rows.slice(0, 6).map(i => (
            <div key={i.symbol} className="flex items-center gap-2 text-xs py-0.5">
              <span className="font-mono font-bold text-foreground w-24 truncate shrink-0">{i.name}</span>
              <RealSparkline symbol={i.symbol} market="US" />
              <span className="flex items-center gap-2 ml-auto">
                <span className="font-mono text-foreground">{fmt(i.price)}</span>
                <span className={cn('font-mono w-14 text-right', tone(i.changePercent))}>{i.changePercent > 0 ? '+' : ''}{fmt(i.changePercent)}%</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ForexPairsWidget() {
  const t = useTopic<{ pairs: ForexRow[] }>('market:forex');
  const rows = t.data?.pairs ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Forex Pairs" hint="MAJORS" />
      {rows.length === 0 ? <EmptyNote>Loading forex…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1">
          {rows.slice(0, 6).map(p => (
            <div key={p.symbol} className="flex items-center justify-between text-xs py-0.5">
              <span className="font-mono font-bold text-foreground">{p.symbol.replace('=X', '')}</span>
              <span className="flex items-center gap-2">
                <span className="font-mono text-foreground">{fmt(p.price, 4)}</span>
                <span className={cn('font-mono w-14 text-right', tone(p.changePct))}>{p.changePct > 0 ? '+' : ''}{fmt(p.changePct)}%</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CryptoMarketsWidget() {
  const t = useTopic<{ indices: IndexRow[] }>('market:indices:CRYPTO');
  const rows = t.data?.indices ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Crypto Markets" hint="CRYPTO" />
      {rows.length === 0 ? <EmptyNote>Loading crypto…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1">
          {rows.slice(0, 6).map(i => (
            <div key={i.symbol} className="flex items-center gap-2 text-xs py-0.5">
              <span className="font-mono font-bold text-foreground w-24 truncate shrink-0">{i.name}</span>
              <RealSparkline symbol={i.symbol} market="CRYPTO" />
              <span className="flex items-center gap-2 ml-auto">
                <span className="font-mono text-foreground">{fmt(i.price)}</span>
                <span className={cn('font-mono w-14 text-right', tone(i.changePercent))}>{i.changePercent > 0 ? '+' : ''}{fmt(i.changePercent)}%</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CommoditiesWidget() {
  const t = useTopic<{ commodities: CommodityRow[] }>('market:commodities');
  const rows = t.data?.commodities ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Commodities" hint="MAJORS" />
      {rows.length === 0 ? <EmptyNote>Loading commodities…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1">
          {rows.slice(0, 6).map(c => (
            <div key={c.symbol} className="flex items-center justify-between text-xs py-0.5">
              <span className="font-mono font-bold text-foreground">{c.name}</span>
              <span className="flex items-center gap-2">
                <span className="font-mono text-foreground">{fmt(c.price)}</span>
                <span className={cn('font-mono w-14 text-right', tone(c.changePct))}>{c.changePct > 0 ? '+' : ''}{fmt(c.changePct)}%</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TopMoversWidget() {
  const t = useTopic<{ groups: OverviewGroup[] }>('market:overview');
  const stocks = useMemo(() => t.data?.groups?.find(g => g.id === 'US')?.stocks ?? [], [t.data]);
  const gainers = useMemo(() => [...stocks].filter(s => s.changePct > 0).sort((a, b) => b.changePct - a.changePct).slice(0, 5), [stocks]);
  const losers = useMemo(() => [...stocks].filter(s => s.changePct < 0).sort((a, b) => a.changePct - b.changePct).slice(0, 5), [stocks]);
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Top Movers" hint="US" />
      {stocks.length === 0 ? <EmptyNote>Loading movers…</EmptyNote> : (
        <div className="grid flex-1 grid-cols-2 gap-2">
          <div>
            <p className="text-[9px] font-bold text-emerald-400 mb-1">Gainers</p>
            {gainers.map(s => (
              <div key={s.symbol} className="flex items-center justify-between text-[10px] py-0.5">
                <span className="font-mono font-bold text-foreground">{s.symbol}</span>
                <span className={cn('font-mono', tone(s.changePct))}>{s.changePct > 0 ? '+' : ''}{fmt(s.changePct)}%</span>
              </div>
            ))}
          </div>
          <div>
            <p className="text-[9px] font-bold text-rose-400 mb-1">Losers</p>
            {losers.map(s => (
              <div key={s.symbol} className="flex items-center justify-between text-[10px] py-0.5">
                <span className="font-mono font-bold text-foreground">{s.symbol}</span>
                <span className={cn('font-mono', tone(s.changePct))}>{s.changePct > 0 ? '+' : ''}{fmt(s.changePct)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function SectorHeatmapWidget() {
  const t = useTopic<{ sectors: { name: string; change: number }[] }>('market:indices:US');
  const sectors = t.data?.sectors ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Sector Heatmap" hint="S&P 500" />
      {sectors.length === 0 ? <EmptyNote>Loading sectors…</EmptyNote> : (
        <div className="grid flex-1 grid-cols-2 gap-1.5 content-start">
          {sectors.map(s => (
            <div key={s.name} className={cn('rounded-lg px-2 py-1.5 text-[10px] font-mono',
              s.change >= 0 ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400')}>
              <span className="block truncate font-bold">{s.name}</span>
              <span>{s.change > 0 ? '+' : ''}{fmt(s.change)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Research ─────────────────────────────────────────────────────────────────

export function NewsFeedWidget() {
  const t = useTopic<{ news: NewsRow[] }>('news:feed');
  const rows = t.data?.news ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="News Feed" hint="LATEST" />
      {rows.length === 0 ? <EmptyNote>Loading news…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto scrollbar-hide">
          {rows.slice(0, 8).map(n => (
            <div key={n.id} className="rounded-xl border border-border/10 glass-card-subtle px-2.5 py-2">
              <p className="text-xs text-foreground leading-snug">{n.headline}</p>
              <div className="mt-1 flex items-center gap-2 text-[9px] text-muted-foreground">
                <span className="font-mono">{n.source}</span>
                {n.ticker && <span className="font-mono text-primary">{n.ticker}</span>}
                <span className={cn('font-mono capitalize', n.sentiment === 'bullish' ? 'text-emerald-400' : n.sentiment === 'bearish' ? 'text-rose-400' : 'text-muted-foreground')}>{n.sentiment}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function EconomicCalendarWidget() {
  const t = useTopic<{ events: CalendarEvent[] }>('econ:calendar');
  const events = t.data?.events ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Economic Calendar" hint="UPCOMING" />
      {events.length === 0 ? <EmptyNote>Loading calendar…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {events.slice(0, 8).map(e => (
            <div key={e.id} className="flex items-center gap-2 text-[10px]">
              <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', e.importance === 'high' ? 'bg-rose-400' : e.importance === 'medium' ? 'bg-amber-400' : 'bg-muted-foreground/40')} />
              <span className="font-mono text-muted-foreground w-8 shrink-0">{e.country}</span>
              <span className="flex-1 truncate text-foreground">{e.title}</span>
              <span className="font-mono text-muted-foreground">{e.forecast ?? '—'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function StockQuoteWidget() {
  const t = useTopic<{ quotes: QuoteRow[] }>('market:quote:AAPL');
  const q = t.data?.quotes?.[0];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Stock Quote" hint="AAPL" />
      {!q || !q.found ? <EmptyNote>Loading quote…</EmptyNote> : (
        <div className="flex flex-1 flex-col justify-center gap-1">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-2xl font-bold text-foreground">{fmt(q.price)}</span>
            <span className={cn('font-mono text-sm font-bold', tone(q.changePercent))}>{q.changePercent > 0 ? '+' : ''}{fmt(q.changePercent)}%</span>
          </div>
          <p className="text-xs text-muted-foreground">{q.name}</p>
        </div>
      )}
    </div>
  );
}

// ── Portfolio ────────────────────────────────────────────────────────────────

export function WatchlistWidget() {
  const t = useTopic<{ quotes: QuoteRow[] }>('market:quote:AAPL,MSFT,NVDA,TSLA,AMZN');
  const quotes = t.data?.quotes ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Watchlist" hint="5 SYM" />
      {quotes.length === 0 ? <EmptyNote>Loading watchlist…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1">
          {quotes.map(q => (
            <div key={q.symbol} className="flex items-center gap-2 text-xs py-0.5">
              <span className="font-mono font-bold text-foreground w-16 truncate shrink-0">{q.symbol}</span>
              <RealSparkline symbol={q.symbol} market="US" />
              <span className="flex items-center gap-2 ml-auto">
                <span className="font-mono text-foreground">{fmt(q.price)}</span>
                <span className={cn('font-mono w-14 text-right', tone(q.changePercent))}>{q.changePercent > 0 ? '+' : ''}{fmt(q.changePercent)}%</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Stubs (external/broker integrations not yet wired) ──────────────────────

export function LiveTVWidget() { return <Unavailable label="Live TV / Streams" />; }
export function RecentFilesWidget() { return <Unavailable label="Recent Files" />; }
export function AgentErrorsWidget() { return <Unavailable label="Agent Errors" />; }
export function WebScraperWidget() { return <Unavailable label="Web Scraper" />; }
export function NotesWidget() { return <Unavailable label="Notes" />; }
export function GeopoliticsWidget() { return <Unavailable label="Geopolitics Events" />; }
export function MaritimeWidget() { return <Unavailable label="Maritime Vessels" />; }
export function PolymarketWidget() { return <Unavailable label="Polymarket" />; }
export function CryptoQuoteStripWidget() { return <Unavailable label="Crypto Ticker" />; }
export function TradeTapeWidget() { return <Unavailable label="Trade Tape" />; }
export function SparklinesWidget() { return <Unavailable label="Sparklines" />; }
export function CandleChartWidget() { return <Unavailable label="Candle Chart" />; }
export function StockScreenerWidget() { return <Unavailable label="Stock Screener" />; }
export function NewsCategoryWidget() { return <Unavailable label="News by Category" />; }
export function PerformanceWidget() { return <Unavailable label="Performance" />; }
export function PortfolioSummaryWidget() { return <Unavailable label="Portfolio Summary" />; }
export function RiskMetricsWidget() { return <Unavailable label="Risk Metrics" />; }
export function HoldingsWidget() { return <Unavailable label="Holdings" />; }

// ── Alerts ──────────────────────────────────────────────────────────────────

interface AlertRow { id: string; name: string; symbols: string[]; active: boolean; status: string; lastFiredAt: string | null; }

export function ActiveAlertsWidget() {
  const t = useTopic<{ alerts: AlertRow[] }>('alerts:list');
  const alerts = t.data?.alerts ?? [];
  const active = alerts.filter(a => a.active);
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Active Alerts" hint={`${active.length}`} />
      {alerts.length === 0 ? <EmptyNote>No alerts configured.</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {active.slice(0, 8).map(a => (
            <div key={a.id} className="flex items-center justify-between text-[10px] rounded-lg border border-border/10 glass-card-subtle px-2 py-1.5">
              <span className="font-mono font-bold text-foreground truncate">{a.name}</span>
              <span className="font-mono text-muted-foreground">{a.symbols.join(', ')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function AlertCountWidget() {
  const t = useTopic<{ alerts: AlertRow[] }>('alerts:list');
  const alerts = t.data?.alerts ?? [];
  const active = alerts.filter(a => a.active).length;
  const triggered = alerts.filter(a => a.status === 'triggered').length;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Alert Count" />
      <div className="grid flex-1 grid-cols-2 gap-2 content-center">
        <div className="rounded-xl glass-card-subtle p-3 text-center">
          <p className="font-mono text-2xl font-bold text-foreground">{active}</p>
          <p className="text-[9px] uppercase tracking-widest text-muted-foreground">Active</p>
        </div>
        <div className="rounded-xl glass-card-subtle p-3 text-center">
          <p className="font-mono text-2xl font-bold text-amber-400">{triggered}</p>
          <p className="text-[9px] uppercase tracking-widest text-muted-foreground">Triggered</p>
        </div>
      </div>
    </div>
  );
}

// ── Journal ─────────────────────────────────────────────────────────────────

interface JournalAnalytics { performance: { winRate: number; netPnl: number; netR: number; profitFactor: number; expectancy: number; averageR: number; totalTrades: number; } }

export function JournalPerformanceWidget() {
  const t = useTopic<{ analytics: JournalAnalytics }>('journal:analytics');
  const p = t.data?.analytics?.performance;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Trading Performance" hint="JOURNAL" />
      {!p ? <EmptyNote>No journal data yet.</EmptyNote> : (
        <div className="grid flex-1 grid-cols-2 gap-2 content-center">
          <StatTile label="Win Rate" value={`${(p.winRate * 100).toFixed(1)}%`} />
          <StatTile label="Net P&L" value={fmt(p.netPnl)} tone={p.netPnl} />
          <StatTile label="Profit Factor" value={p.profitFactor === Infinity ? '∞' : fmt(p.profitFactor)} />
          <StatTile label="Expectancy" value={`${fmt(p.expectancy)}R`} tone={p.expectancy} />
          <StatTile label="Avg R" value={`${fmt(p.averageR)}R`} tone={p.averageR} />
          <StatTile label="Trades" value={String(p.totalTrades)} />
        </div>
      )}
    </div>
  );
}

function StatTile({ label, value, tone: t }: { label: string; value: string; tone?: number }) {
  return (
    <div className="rounded-xl glass-card-subtle p-2.5">
      <p className="text-[9px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className={cn('font-mono text-sm font-bold', t == null ? 'text-foreground' : t > 0 ? 'text-emerald-400' : t < 0 ? 'text-rose-400' : 'text-foreground')}>{value}</p>
    </div>
  );
}

// ── Global / Macro ──────────────────────────────────────────────────────────

export function GlobalMarketsWidget() {
  const t = useTopic<{ groups: OverviewGroup[] }>('market:overview');
  const groups = t.data?.groups ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Global Markets" hint="WORLD" />
      {groups.length === 0 ? <EmptyNote>Loading global markets…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto scrollbar-hide">
          {groups.slice(0, 10).map(g => {
            const top = g.stocks[0];
            return (
              <div key={g.id} className="flex items-center justify-between text-[10px] py-0.5">
                <span className="font-mono font-bold text-foreground">{g.name ?? g.country}</span>
                {top && <span className={cn('font-mono', tone(top.changePct))}>{top.changePct > 0 ? '+' : ''}{fmt(top.changePct)}%</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function MarketStatusWidget() {
  const t = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const rows = t.data?.indices ?? [];
  const up = rows.filter(i => i.changePercent > 0).length;
  const down = rows.filter(i => i.changePercent < 0).length;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Market Status" hint="US" />
      <div className="flex flex-1 flex-col justify-center gap-2">
        <div className="flex items-center gap-2">
          <span className={cn('h-2.5 w-2.5 rounded-full', up >= down ? 'bg-emerald-400' : 'bg-rose-400')} />
          <span className="text-xs text-muted-foreground">{up >= down ? 'Risk On' : 'Risk Off'}</span>
        </div>
        <div className="flex gap-4 text-[10px]">
          <span className="text-emerald-400">{up} advancing</span>
          <span className="text-rose-400">{down} declining</span>
        </div>
      </div>
    </div>
  );
}

// ── AI / Agent widgets moved to ai-widgets.tsx (real agent state) ────────────
