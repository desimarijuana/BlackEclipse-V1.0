'use client';

// ── Dashboard widget renderers ───────────────────────────────────────────────
// Real data widgets for the Command Center catalog. Each consumes DataHub
// topics and reports null/empty where data is missing — never fabricates.
// Widgets needing external/broker integrations (not yet wired) render a clear
// UNAVAILABLE state instead of fake data.

import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ChevronDown, Search, Star, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChartPalette } from '@/lib/chart-palette-store';
import { useTopic, registerTopic, jsonTopic } from '@/lib/workspace/data-hub';
import { useWatchlist } from './watchlist-store';
import { useAggregatePortfolio } from './portfolio-store';
import { useMarketIndices, useMarketGroup, useMarketSectors, marketViewName } from './market-views';
import { MarketPicker } from '@/components/workspace/market-picker';
import type { WidgetPlacement } from '@/lib/workspace/types';

const UP = 'text-emerald-400';
const DOWN = 'text-rose-400';
const tone = (n: number) => (n > 0 ? UP : n < 0 ? DOWN : 'text-muted-foreground');
const fmt = (n?: number | null, d = 2) => (n == null || !Number.isFinite(n) ? '—' : n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));

function WidgetHeader({ title, hint, right }: { title: string; hint?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>
      <span className="flex items-center gap-2 shrink-0">
        {hint && (typeof hint === 'string'
          ? <span className="font-mono text-[9px] text-muted-foreground/70">{hint}</span>
          : hint)}
        {right}
      </span>
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

/** Inline SVG area sparkline — line + soft gradient fill, green up / red down.
 *  `fluid` stretches it to fill its flex parent (viewBox scaled, stroke kept 1px). */
export function Sparkline({ points, width = 96, height = 24, fluid = false, className }: { points: number[]; width?: number; height?: number; fluid?: boolean; className?: string }) {
  const palette = useChartPalette();
  const gradientId = `spark-${useId().replace(/:/g, '')}`;
  const clean = points.filter(p => Number.isFinite(p) && p > 0);
  const svgProps = fluid
    ? { width: '100%', viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: 'none' as const }
    : { width, height };
  if (clean.length < 2) return <span className={cn('inline-block', className)} style={{ height }} />;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const range = max - min || 1;
  const step = width / (clean.length - 1);
  const coords = clean.map((p, i) => [(i * step), (height - ((p - min) / range) * height)] as const);
  const line = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${width.toFixed(1)},${height} L0,${height} Z`;
  const change = clean[clean.length - 1] - clean[0];
  const color = change > 0 ? palette.candles.up : change < 0 ? palette.candles.down : palette.candles.neutral;
  return (
    <svg
      {...svgProps}
      height={fluid ? height : undefined}
      className={cn('shrink-0', className)}
      aria-hidden
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} stroke="none" />
      <path d={line} fill="none" stroke={color} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Fetches REAL price history for a symbol and renders a sparkline of actual closes. */
const sparkCache = new Map<string, number[]>();
export function RealSparkline({ symbol, market = 'US', width = 96, height = 24, fluid = false, className }: { symbol: string; market?: string; width?: number; height?: number; fluid?: boolean; className?: string }) {
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
  return <Sparkline points={points} width={width} height={height} fluid={fluid} className={className} />;
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

export function MarketIndicesWidget({ placement }: { placement?: WidgetPlacement }) {
  const { market, rows } = useMarketIndices(placement);
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Market Indices" hint={<MarketPicker placement={placement} />} />
      {rows.length === 0 ? <EmptyNote>Loading indices…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1">
          {rows.slice(0, 6).map(i => (
            <div key={i.symbol} className="flex items-center gap-2 text-xs py-0.5">
              <span className="font-mono font-bold text-foreground w-24 truncate shrink-0">{i.name}</span>
              <div className="min-w-0 flex-1">
                <RealSparkline symbol={i.symbol} market={market} fluid width={160} height={30} />
              </div>
              <span className="flex items-center gap-2 shrink-0">
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
              <div className="min-w-0 flex-1">
                <RealSparkline symbol={i.symbol} market="CRYPTO" fluid width={160} height={30} />
              </div>
              <span className="flex items-center gap-2 shrink-0">
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

export function TopMoversWidget({ placement }: { placement?: WidgetPlacement }) {
  const { stocks } = useMarketGroup(placement);
  const gainers = useMemo(() => [...stocks].filter(s => s.changePct > 0).sort((a, b) => b.changePct - a.changePct).slice(0, 5), [stocks]);
  const losers = useMemo(() => [...stocks].filter(s => s.changePct < 0).sort((a, b) => a.changePct - b.changePct).slice(0, 5), [stocks]);
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Top Movers" hint={<MarketPicker placement={placement} />} />
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

export function SectorHeatmapWidget({ placement }: { placement?: WidgetPlacement }) {
  // Sector performance rides along on the same /api/indices payload — no extra fetch.
  const { sectors } = useMarketSectors(placement);
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Sector Heatmap" hint={<MarketPicker placement={placement} />} />
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

const NEWS_SENTIMENTS = [
  { id: '', label: 'All' },
  { id: 'bullish', label: 'Bullish' },
  { id: 'bearish', label: 'Bearish' },
  { id: 'neutral', label: 'Neutral' },
] as const;

const NEWS_CATEGORIES = [
  'MARKETS', 'STOCKS', 'BONDS', 'FOREX', 'CRYPTO', 'COMMODITIES',
  'ECONOMIC', 'INFLATION', 'CENTRAL BANKS', 'JOBS', 'TRADE',
  'GEOPOLITICS', 'WAR', 'POLITICS', 'REGULATORY', 'TECH', 'AI',
  'ENERGY', 'HEALTHCARE',
];

export function NewsFeedWidget() {
  const t = useTopic<{ news: NewsRow[] }>('news:feed');
  const rows = useMemo(() => t.data?.news ?? [], [t.data]);
  const [sentiment, setSentiment] = useState('');
  const [category, setCategory] = useState('');

  const filtered = useMemo(
    () => rows.filter(n =>
      (!sentiment || n.sentiment === sentiment) &&
      (!category || (n.category ?? '').toUpperCase() === category)),
    [rows, sentiment, category],
  );

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="News Feed" hint={rows.length ? `${filtered.length}/${rows.length}` : 'LATEST'} />

      {/* Filters — pick the sentiment / topic that matters for the decision at hand. */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {NEWS_SENTIMENTS.map(s => (
          <button
            key={s.id || 'all'}
            type="button"
            onClick={() => setSentiment(s.id)}
            className={cn(
              'cursor-pointer rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide transition-colors',
              sentiment === s.id
                ? s.id === 'bullish'
                  ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-400'
                  : s.id === 'bearish'
                    ? 'border-rose-500/40 bg-rose-500/15 text-rose-400'
                    : 'border-primary/40 bg-primary/15 text-primary'
                : 'border-border/20 text-muted-foreground hover:text-foreground',
            )}
          >
            {s.label}
          </button>
        ))}
        <div className="relative ml-auto shrink-0">
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            title="Filter headlines by topic"
            className="cursor-pointer appearance-none rounded-full border border-border/20 bg-background/60 py-0.5 pl-2 pr-5 text-[9px] font-bold uppercase tracking-wide text-muted-foreground outline-none transition-colors hover:text-foreground focus:ring-1 focus:ring-primary"
          >
            <option value="" className="bg-[#121212] text-foreground">All topics</option>
            {NEWS_CATEGORIES.map(c => (
              <option key={c} value={c} className="bg-[#121212] text-foreground">{c}</option>
            ))}
          </select>
          <ChevronDown size={9} className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        </div>
      </div>

      {rows.length === 0 ? <EmptyNote>Loading news…</EmptyNote> : filtered.length === 0 ? (
        <EmptyNote>No headlines match these filters.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto scrollbar-hide">
          {filtered.slice(0, 8).map(n => (
            <div key={n.id} className="rounded-xl border border-border/10 glass-card-subtle px-2.5 py-2">
              <p className="text-xs text-foreground leading-snug">{n.headline}</p>
              <div className="mt-1 flex items-center gap-2 text-[9px] text-muted-foreground">
                <span className="font-mono">{n.source}</span>
                {n.ticker && <span className="font-mono text-primary">{n.ticker}</span>}
                <span className={cn('font-mono capitalize', n.sentiment === 'bullish' ? 'text-emerald-400' : n.sentiment === 'bearish' ? 'text-rose-400' : 'text-muted-foreground')}>{n.sentiment}</span>
                {n.category && <span className="ml-auto font-mono uppercase tracking-wide text-muted-foreground/60">{n.category}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function econDateLabel(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '—';
  const d = new Date(ts);
  const now = new Date();
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const tomorrow = new Date(now.getTime() + 86_400_000);
  const day = sameDay(d, now) ? 'Today' : sameDay(d, tomorrow) ? 'Tomorrow' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${day} ${time}`;
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
              <span className="font-mono text-muted-foreground/70 w-[74px] shrink-0">{econDateLabel(e.date)}</span>
              <span className="font-mono text-muted-foreground w-6 shrink-0">{e.country}</span>
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

/** Compact inline symbol search — used to add symbols straight from the widget. */
function AddSymbolInput({ onAdd, existing }: { onAdd: (s: string) => void; existing: string[] }) {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<{ symbol: string; name: string; marketId: string }[]>([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 1) { setSuggestions([]); return; }
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/quote?q=${encodeURIComponent(q)}`);
        const d = await r.json();
        setSuggestions((d.suggestions ?? []).filter((s: { symbol: string }) => !existing.includes(s.symbol.toUpperCase())));
        setOpen(true);
      } catch { setSuggestions([]); }
    }, 200);
    return () => clearTimeout(t);
  }, [query, existing]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const commit = (s: string) => { onAdd(s); setQuery(''); setSuggestions([]); setOpen(false); };

  return (
    <div className="relative min-w-0 flex-1" ref={boxRef}>
      <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        onFocus={() => { if (suggestions.length) setOpen(true); }}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); if (query.trim()) commit(query.trim().toUpperCase()); } }}
        placeholder="Add symbol…"
        className="w-full rounded-lg border border-border/30 bg-background/60 py-1 pl-6 pr-2 text-[10px] font-mono text-foreground outline-none focus:ring-1 focus:ring-primary"
      />
      {open && suggestions.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-40 overflow-y-auto rounded-lg border border-white/10 glass-card-strong p-1 shadow-2xl shadow-black/40">
          {suggestions.slice(0, 8).map(s => (
            <button
              key={`${s.symbol}-${s.marketId}`}
              type="button"
              onClick={() => commit(s.symbol)}
              className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-[10px] hover:bg-accent/50 cursor-pointer"
            >
              <span className="font-mono font-bold text-foreground">{s.symbol}</span>
              <span className="truncate text-muted-foreground">{s.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function WatchlistWidget() {
  const { items, add, remove, toggleFavorite } = useWatchlist();
  const [favOnly, setFavOnly] = useState(false);
  const symbols = useMemo(() => items.map(i => i.symbol), [items]);
  const key = symbols.join(',');
  const topicId = key ? `market:quote:${key}` : 'market:quote:__empty__';

  // Register the per-symbol-set topic synchronously (idempotent) so `useTopic`
  // below can subscribe on its first effect pass.
  useMemo(() => {
    if (!key) return;
    registerTopic(jsonTopic(topicId, `/api/quote?symbols=${encodeURIComponent(key)}`, { ttl: 60_000, interval: 30_000 }));
  }, [topicId, key]);

  const t = useTopic<{ quotes: QuoteRow[] }>(topicId);
  const quoteMap = useMemo(() => new Map((t.data?.quotes ?? []).map(q => [q.symbol, q])), [t.data]);

  const visible = useMemo(() => {
    const rows = items.map((it, idx) => ({ ...it, q: quoteMap.get(it.symbol), idx }));
    rows.sort((a, b) => Number(Boolean(b.favorite)) - Number(Boolean(a.favorite)) || a.idx - b.idx);
    return favOnly ? rows.filter(r => r.favorite) : rows;
  }, [items, quoteMap, favOnly]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Watchlist" hint={items.length ? `${items.length} SYM` : 'EMPTY'} />

      <div className="mb-2 flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setFavOnly(v => !v)}
          className={cn(
            'inline-flex shrink-0 items-center gap-1 rounded-lg border px-2 py-1 text-[9px] font-bold uppercase tracking-wide transition-colors cursor-pointer',
            favOnly ? 'border-amber-400/40 bg-amber-400/15 text-amber-400' : 'border-border/20 text-muted-foreground hover:text-foreground',
          )}
          title="Show favourites only"
        >
          <Star size={10} className={favOnly ? 'fill-amber-400' : ''} /> Favs
        </button>
        <AddSymbolInput onAdd={add} existing={symbols} />
      </div>

      {items.length === 0 ? (
        <EmptyNote>Add a symbol above to start your watchlist.</EmptyNote>
      ) : visible.length === 0 ? (
        <EmptyNote>No favourites yet — tap the star on a symbol.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto scrollbar-hide">
          {visible.map(({ symbol, favorite, q }) => (
            <div key={symbol} className="group flex items-center gap-1.5 text-xs py-1">
              <button
                type="button"
                onClick={() => toggleFavorite(symbol)}
                className={cn('shrink-0 cursor-pointer transition-colors', favorite ? 'text-amber-400' : 'text-muted-foreground/30 hover:text-amber-400')}
                title={favorite ? 'Remove from favourites' : 'Add to favourites'}
              >
                <Star size={11} className={favorite ? 'fill-amber-400' : ''} />
              </button>
              <span className="font-mono font-bold text-foreground w-14 truncate shrink-0">{symbol}</span>
              <div className="min-w-0 flex-1">
                <RealSparkline symbol={symbol} market="US" fluid width={160} height={34} />
              </div>
              <span className="font-mono text-foreground shrink-0">{q ? fmt(q.price) : '—'}</span>
              <span className={cn('font-mono w-14 text-right shrink-0', q ? tone(q.changePercent) : 'text-muted-foreground')}>
                {q ? `${q.changePercent > 0 ? '+' : ''}${fmt(q.changePercent)}%` : '—'}
              </span>
              <button
                type="button"
                onClick={() => remove(symbol)}
                className="shrink-0 cursor-pointer text-muted-foreground/40 opacity-0 transition-opacity group-hover:opacity-100 hover:text-rose-400"
                title={`Remove ${symbol}`}
              >
                <X size={11} />
              </button>
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

// ── Portfolio widgets (real — read the guest fund book + live JDDS quotes) ──

const ALLOCATION_PALETTE = ['#34d399', '#60a5fa', '#fbbf24', '#f472b6', '#a78bfa', '#fb7185', '#2dd4bf', '#f97316', '#4ade80', '#e879f9', '#38bdf8', '#facc15'];

function AllocationBar({ holdings }: { holdings: Array<{ symbol: string; allocation: number }> }) {
  const top = holdings.slice(0, 10);
  const rest = holdings.slice(10).reduce((a, h) => a + h.allocation, 0);
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-accent/40">
      {top.map((h, i) => (
        <div
          key={h.symbol}
          className="h-full"
          style={{ width: `${h.allocation}%`, backgroundColor: ALLOCATION_PALETTE[i % ALLOCATION_PALETTE.length] }}
          title={`${h.symbol} ${h.allocation.toFixed(1)}%`}
        />
      ))}
      {rest > 0 && <div className="h-full bg-muted-foreground/40" style={{ width: `${rest}%` }} title={`Other ${rest.toFixed(1)}%`} />}
    </div>
  );
}

export function PortfolioSummaryWidget() {
  const { stats, funds } = useAggregatePortfolio();
  const has = stats.holdings.length > 0 || stats.totalValue > 0;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Portfolio Summary" hint={`${funds.length} FUNDS`} />
      {!has ? <EmptyNote>No positions yet — add transactions in the Portfolio page.</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-3">
          <div>
            <p className="text-[9px] uppercase tracking-widest text-muted-foreground">Total value (USD)</p>
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-2xl font-bold text-foreground">${fmt(stats.totalValue)}</span>
              <span className={cn('font-mono text-xs font-bold', tone(stats.dailyChangePercent))}>
                {stats.dailyChangePercent > 0 ? '+' : ''}{fmt(stats.dailyChangePercent)}%
              </span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <StatTile label="Unrealized" value={`$${fmt(stats.unrealizedPnL)}`} tone={stats.unrealizedPnL} />
            <StatTile label="Realized" value={`$${fmt(stats.realizedPnL)}`} tone={stats.realizedPnL} />
            <StatTile label="Cost basis" value={`$${fmt(stats.costBasis)}`} />
            <StatTile label="ROI" value={`${fmt(stats.roiPercent)}%`} tone={stats.roiPercent} />
          </div>
          <div>
            <p className="mb-1.5 text-[9px] uppercase tracking-widest text-muted-foreground">Allocation</p>
            <AllocationBar holdings={stats.holdings} />
          </div>
        </div>
      )}
    </div>
  );
}

export function HoldingsWidget() {
  const { stats } = useAggregatePortfolio();
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Holdings" hint={`${stats.holdings.length}`} />
      {stats.holdings.length === 0 ? <EmptyNote>No open positions.</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto scrollbar-hide">
          {stats.holdings.slice(0, 12).map(h => (
            <div key={h.symbol} className="flex items-center gap-2 text-[10px] py-0.5">
              <span className="font-mono font-bold text-foreground w-14 truncate shrink-0">{h.symbol}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-accent/40">
                <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, h.allocation)}%` }} />
              </div>
              <span className="font-mono text-muted-foreground w-10 text-right shrink-0">{fmt(h.allocation, 1)}%</span>
              <span className="font-mono text-foreground w-20 text-right shrink-0">${fmt(h.valueUsd)}</span>
              <span className={cn('font-mono w-14 text-right shrink-0', tone(h.dayPct))}>{h.dayPct > 0 ? '+' : ''}{fmt(h.dayPct)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function PerformanceWidget() {
  const { stats } = useAggregatePortfolio();
  const has = stats.totalValue > 0 || stats.realizedPnL !== 0;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Performance" hint="ALL FUNDS" />
      {!has ? <EmptyNote>No performance data yet.</EmptyNote> : (
        <div className="grid flex-1 grid-cols-2 gap-2 content-center">
          <StatTile label="Day P&L" value={`$${fmt(stats.dailyChangeValue)}`} tone={stats.dailyChangeValue} />
          <StatTile label="Day %" value={`${fmt(stats.dailyChangePercent)}%`} tone={stats.dailyChangePercent} />
          <StatTile label="Unrealized" value={`$${fmt(stats.unrealizedPnL)}`} tone={stats.unrealizedPnL} />
          <StatTile label="Realized" value={`$${fmt(stats.realizedPnL)}`} tone={stats.realizedPnL} />
          <StatTile label="Dividends" value={`$${fmt(stats.dividendsUsd)}`} tone={stats.dividendsUsd} />
          <StatTile label="ROI" value={`${fmt(stats.roiPercent)}%`} tone={stats.roiPercent} />
        </div>
      )}
    </div>
  );
}

export function RiskMetricsWidget() {
  const { stats } = useAggregatePortfolio();
  const holdings = stats.holdings;
  const top = holdings[0];
  // Herfindahl concentration → diversification score (100 = perfectly spread).
  const hhi = holdings.reduce((a, h) => a + (h.allocation / 100) ** 2, 0);
  const diversification = holdings.length > 1 ? (1 - hhi) * 100 : 0;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Risk Metrics" hint={`${holdings.length} POS`} />
      {holdings.length === 0 ? <EmptyNote>No positions to analyse.</EmptyNote> : (
        <div className="grid flex-1 grid-cols-2 gap-2 content-center">
          <StatTile label="Positions" value={String(holdings.length)} />
          <StatTile label="Diversification" value={`${fmt(diversification, 0)}%`} />
          <StatTile label="Largest weight" value={top ? `${fmt(top.allocation, 1)}%` : '—'} />
          <StatTile label="Largest" value={top?.symbol ?? '—'} />
          <StatTile label="Unrealized" value={`$${fmt(stats.unrealizedPnL)}`} tone={stats.unrealizedPnL} />
          <StatTile label="ROI" value={`${fmt(stats.roiPercent)}%`} tone={stats.roiPercent} />
        </div>
      )}
    </div>
  );
}

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
                <span className="font-mono font-bold text-foreground" title={g.name ?? g.country}>{marketViewName(g.id)}</span>
                {top && <span className={cn('font-mono', tone(top.changePct))}>{top.changePct > 0 ? '+' : ''}{fmt(top.changePct)}%</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function MarketStatusWidget({ placement }: { placement?: WidgetPlacement }) {
  const { rows } = useMarketIndices(placement);
  const up = rows.filter(i => i.changePercent > 0).length;
  const down = rows.filter(i => i.changePercent < 0).length;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Market Status" hint={<MarketPicker placement={placement} />} />
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
