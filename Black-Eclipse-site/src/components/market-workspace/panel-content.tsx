'use client';

// ── Panel content — the non-chart workspace panels ───────────────────────────
// Every panel type except `chart`. All data comes from the existing JDdS APIs /
// DataHub topics — no new market-data system. Panels that need an integration
// that does not exist render a clear UNAVAILABLE state rather than fabricating.

import React, { useMemo, useState } from 'react';
import {
  Bell, CalendarDays, DollarSign, Layers, LineChart, Newspaper, Search, Star, X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useTopic } from '@/lib/workspace/data-hub';
import { useQuoteBatch } from '@/lib/chart/subscription-manager';
import { useWatchlist } from '@/lib/dashboard/watchlist-store';
import { useAggregatePortfolio } from '@/lib/dashboard/portfolio-store';
import { MarketHeatmapWidget } from '@/lib/dashboard/heatmap-widget';
import { formatPercent, instrumentMeta, toneClass } from '@/lib/market-workspace/instruments';
import type { MarketPanel } from '@/lib/market-workspace/types';
import { SymbolSelector } from '@/components/chart/symbol-selector';
import { AiPanel } from './ai-panel';

interface IndexRow { name: string; symbol: string; price: number; change: number; changePercent: number; currency?: string; }
interface OverviewGroup { id: string; country: string; name?: string; stocks: { symbol: string; name: string; price: number; changePct: number }[]; }
interface NewsRow { id: string; source: string; ticker?: string; timestamp: string; headline: string; sentiment: 'bullish' | 'bearish' | 'neutral'; }
interface CalendarEvent { id: string; title: string; country: string; date: string; importance: 'low' | 'medium' | 'high'; forecast?: string | null; actual?: string | null; }
interface AssetDetail {
  found: boolean;
  asset?: {
    symbol: string; name: string; sector: string; industry: string; marketId: string; currency: string;
    price: number; changePercent: number; volume: string; marketCap: string; peRatio: string; forwardPE: string;
    dividendYield: string; eps: string; beta: string; dayHigh: number | null; dayLow: number | null;
    fiftyTwoWeekHigh: number | null; fiftyTwoWeekLow: number | null; securityType: string; source: string | null; updatedAt: string | null;
  };
}

function PanelTitle({ icon: Icon, title, hint }: { icon: React.ElementType; title: string; hint?: string }) {
  return (
    <div className="flex shrink-0 items-center gap-1.5 border-b border-border/10 px-3 py-2">
      <Icon size={12} className="text-primary" />
      <span className="font-serif text-xs font-semibold text-foreground">{title}</span>
      {hint && <span className="ml-auto font-mono text-[9px] text-muted-foreground/70">{hint}</span>}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-1 items-center justify-center p-4 text-center text-[11px] italic text-muted-foreground/70">{children}</div>;
}

function Unavailable({ label }: { label: string }) {
  return (
    <div className="flex flex-1 items-center justify-center p-4 text-center">
      <p className="text-[11px] italic text-amber-400/80">UNAVAILABLE — {label}.</p>
    </div>
  );
}

// ── Watchlist (drag a row onto a chart panel) ────────────────────────────────

function WatchlistPanel({ onPick }: { onPick?: (symbol: string) => void }) {
  const { items, add, remove, toggleFavorite } = useWatchlist();
  const { rows } = useQuoteBatch(items.map(i => i.symbol));
  const [dragSymbol, setDragSymbol] = useState<string | null>(null);

  const quoteMap = useMemo(() => new Map(rows.map(r => [r.symbol.toUpperCase(), r])), [rows]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PanelTitle icon={Star} title="Watchlist" hint={`${items.length} SYM`} />
      <div className="flex shrink-0 items-center gap-1 px-2 py-1.5">
        <div className="min-w-0 flex-1">
          <SymbolSelector compact placeholder="Add symbol…" onPick={(s) => add(s)} showMarket={false} inline />
        </div>
      </div>
      {items.length === 0 ? (
        <Empty>Add a symbol to start your watchlist.</Empty>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto scrollbar-hide px-1.5 pb-2">
          {items.map(({ symbol, favorite }) => {
            const q = quoteMap.get(symbol.toUpperCase());
            const meta = instrumentMeta(symbol, q?.marketId ?? 'US');
            return (
              <div
                key={symbol}
                draggable
                onDragStart={(e) => {
                  setDragSymbol(symbol);
                  e.dataTransfer.effectAllowed = 'copy';
                  e.dataTransfer.setData('text/plain', JSON.stringify({ symbol, market: q?.marketId ?? 'US' }));
                }}
                onDragEnd={() => setDragSymbol(null)}
                onClick={() => onPick?.(symbol)}
                className={cn(
                  'group flex cursor-grab items-center gap-1.5 rounded-lg px-1.5 py-1 text-[11px] transition-colors hover:bg-accent/40',
                  dragSymbol === symbol && 'opacity-50',
                )}
                title={`Drag ${symbol} onto a chart`}
              >
                <button
                  onClick={(e) => { e.stopPropagation(); toggleFavorite(symbol); }}
                  className={cn('shrink-0 cursor-pointer', favorite ? 'text-amber-400' : 'text-muted-foreground/30 hover:text-amber-400')}
                >
                  <Star size={10} weight={favorite ? 'fill' : 'regular'} />
                </button>
                <span className="w-14 shrink-0 truncate font-mono font-bold text-foreground">{symbol}</span>
                <span className="min-w-0 flex-1 truncate text-[9px] text-muted-foreground">{q?.name ?? ''}</span>
                <span className="shrink-0 font-mono tabular-nums text-foreground/90">
                  {q?.found ? q.price.toLocaleString('en-US', { minimumFractionDigits: meta.decimals, maximumFractionDigits: meta.decimals }) : '—'}
                </span>
                <span className={cn('w-12 shrink-0 text-right font-mono tabular-nums', toneClass(q?.changePercent))}>
                  {q?.found ? formatPercent(q.changePercent) : '—'}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); remove(symbol); }}
                  className="hidden shrink-0 cursor-pointer text-muted-foreground/50 hover:text-rose-400 group-hover:block"
                >
                  <X size={10} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Market Overview ──────────────────────────────────────────────────────────

function MarketOverviewPanel() {
  const overview = useTopic<{ groups: OverviewGroup[] }>('market:overview');
  const indices = useTopic<{ indices: IndexRow[] }>('market:indices:US');
  const groups = overview.data?.groups ?? [];
  const rows = indices.data?.indices ?? [];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PanelTitle icon={LineChart} title="Market Overview" hint="GLOBAL" />
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto scrollbar-hide p-2">
        <div>
          <span className="mb-1 block text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Indices</span>
          <div className="flex flex-col gap-0.5">
            {rows.slice(0, 8).map(i => (
              <div key={i.symbol} className="flex items-center justify-between text-[11px]">
                <span className="font-mono text-foreground">{i.name}</span>
                <span className="flex items-center gap-2">
                  <span className="font-mono tabular-nums text-foreground/90">{i.price ? i.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                  <span className={cn('w-14 text-right font-mono tabular-nums', toneClass(i.changePercent))}>{formatPercent(i.changePercent)}</span>
                </span>
              </div>
            ))}
            {rows.length === 0 && <p className="py-3 text-center text-[10px] italic text-muted-foreground/60">Loading indices…</p>}
          </div>
        </div>
        <div>
          <span className="mb-1 block text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Markets</span>
          <div className="flex flex-col gap-0.5">
            {groups.slice(0, 8).map(g => (
              <div key={g.id} className="flex items-center justify-between text-[11px]">
                <span className="font-mono text-foreground">{g.name ?? g.country}</span>
                <span className={cn('font-mono tabular-nums', toneClass(g.stocks[0]?.changePct))}>{formatPercent(g.stocks[0]?.changePct)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── News ─────────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const mins = Math.floor((Date.now() - ts) / 60000);
  if (mins < 60) return `${Math.max(1, mins)}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function NewsPanel({ symbol }: { symbol?: string }) {
  const t = useTopic<{ items: NewsRow[] }>('news:feed');
  const items = useMemo(() => {
    const all = t.data?.items ?? [];
    return symbol ? all.filter(n => n.ticker?.toUpperCase() === symbol.toUpperCase()) : all;
  }, [t.data, symbol]);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PanelTitle icon={Newspaper} title="News" hint={symbol ? symbol : 'LATEST'} />
      {items.length === 0 ? (
        <Empty>{symbol ? `No headlines for ${symbol} right now.` : 'Loading headlines…'}</Empty>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide p-2">
          {items.slice(0, 30).map(n => (
            <a
              key={n.id}
              href={undefined}
              className={cn('rounded-lg border-l-2 px-2 py-1.5', n.sentiment === 'bullish' ? 'border-emerald-400/50' : n.sentiment === 'bearish' ? 'border-rose-400/50' : 'border-border/30')}
            >
              <p className="text-[11px] leading-snug text-foreground">{n.headline}</p>
              <div className="mt-0.5 flex items-center gap-2 text-[9px] text-muted-foreground">
                <span className="font-bold uppercase">{n.source}</span>
                {n.ticker && <span className="font-mono text-primary">{n.ticker}</span>}
                <span className="ml-auto">{relativeTime(n.timestamp)}</span>
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Fundamentals ─────────────────────────────────────────────────────────────

function FundamentalsPanel({ symbol, market }: { symbol: string; market: string }) {
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [loading, setLoading] = useState(true);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams({ symbol, ...(market ? { market } : {}) });
    fetch(`/api/asset-details?${params.toString()}`)
      .then(r => (r.ok ? r.json() : { found: false }))
      .then((j: AssetDetail) => { if (!cancelled) setDetail(j); })
      .catch(() => { if (!cancelled) setDetail({ found: false }); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, market]);

  if (loading) return <div className="flex min-h-0 flex-1 flex-col"><PanelTitle icon={Layers} title="Fundamentals" hint={symbol} /><Empty>Loading…</Empty></div>;
  const a = detail?.asset;
  if (!detail?.found || !a) return <div className="flex min-h-0 flex-1 flex-col"><PanelTitle icon={Layers} title="Fundamentals" hint={symbol} /><Unavailable label="no fundamentals for this instrument" /></div>;

  const rows: Array<[string, string]> = [
    ['Price', `${a.currency} ${a.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`],
    ['Change', formatPercent(a.changePercent)],
    ['Market Cap', a.marketCap],
    ['Volume', a.volume],
    ['P/E', a.peRatio],
    ['Fwd P/E', a.forwardPE],
    ['EPS', a.eps],
    ['Beta', a.beta],
    ['Div Yield', a.dividendYield],
    ['Sector', a.sector],
    ['Industry', a.industry],
    ['Type', a.securityType],
  ];
  if (a.fiftyTwoWeekLow != null && a.fiftyTwoWeekHigh != null) {
    rows.push(['52W Range', `${a.fiftyTwoWeekLow.toFixed(2)} – ${a.fiftyTwoWeekHigh.toFixed(2)}`]);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PanelTitle icon={Layers} title="Fundamentals" hint={a.symbol} />
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto scrollbar-hide p-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between border-b border-border/5 py-1 text-[11px]">
            <span className="text-muted-foreground">{label}</span>
            <span className="font-mono tabular-nums text-foreground/90">{value}</span>
          </div>
        ))}
        {a.source && <p className="mt-2 text-[9px] uppercase tracking-wide text-muted-foreground/50">Source: {a.source}</p>}
      </div>
    </div>
  );
}

// ── Economic Calendar ────────────────────────────────────────────────────────

function EconomicCalendarPanel() {
  const t = useTopic<{ events: CalendarEvent[] }>('econ:calendar');
  const events = t.data?.events ?? [];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PanelTitle icon={CalendarDays} title="Economic Calendar" hint={`${events.length} EVENTS`} />
      {events.length === 0 ? <Empty>Loading calendar…</Empty> : (
        <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto scrollbar-hide p-2">
          {events.slice(0, 40).map(e => (
            <div key={e.id} className="flex items-center gap-2 text-[11px]">
              <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', e.importance === 'high' ? 'bg-rose-400' : e.importance === 'medium' ? 'bg-amber-400' : 'bg-muted-foreground/40')} />
              <span className="w-16 shrink-0 font-mono text-muted-foreground/70">{e.date}</span>
              <span className="w-6 shrink-0 font-mono text-muted-foreground">{e.country}</span>
              <span className="min-w-0 flex-1 truncate text-foreground">{e.title}</span>
              <span className="shrink-0 font-mono text-muted-foreground">{e.forecast ?? '—'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Portfolio ────────────────────────────────────────────────────────────────

function PortfolioPanel() {
  const { stats, quotes } = useAggregatePortfolio();
  const rows = quotes.slice(0, 30);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PanelTitle icon={DollarSign} title="Portfolio" hint={`${quotes.length} HOLDINGS`} />
      <div className="grid shrink-0 grid-cols-2 gap-1.5 p-2 sm:grid-cols-4">
        <Stat label="Value" value={stats.totalValue.toLocaleString('en-US', { maximumFractionDigits: 0 })} tone="neutral" />
        <Stat label="Unreal. P&L" value={stats.unrealizedPnL.toLocaleString('en-US', { maximumFractionDigits: 0 })} tone={stats.unrealizedPnL >= 0 ? 'up' : 'down'} />
        <Stat label="Day" value={formatPercent(stats.dailyChangePercent)} tone={stats.dailyChangePercent >= 0 ? 'up' : 'down'} />
        <Stat label="ROI" value={formatPercent(stats.roiPercent)} tone={stats.roiPercent >= 0 ? 'up' : 'down'} />
      </div>
      {rows.length === 0 ? (
        <Empty>Add holdings in the Portfolio page.</Empty>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto scrollbar-hide px-2 pb-2">
          {rows.map(q => (
            <div key={q.symbol} className="flex items-center justify-between text-[11px]">
              <span className="font-mono font-bold text-foreground">{q.symbol}</span>
              <span className="font-mono tabular-nums text-foreground/90">{q.price.toLocaleString('en-US', { maximumFractionDigits: 2 })}</span>
              <span className={cn('w-14 text-right font-mono tabular-nums', toneClass(q.changePercent))}>{formatPercent(q.changePercent)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: 'up' | 'down' | 'neutral' }) {
  return (
    <div className="rounded-lg border border-border/10 glass-card-subtle px-2 py-1.5">
      <span className="block text-[9px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className={cn('font-mono text-xs font-bold', tone === 'up' ? 'text-emerald-400' : tone === 'down' ? 'text-rose-400' : 'text-foreground')}>{value}</span>
    </div>
  );
}

// ── Alerts ───────────────────────────────────────────────────────────────────

interface AlertRow { id: string; symbol: string; condition: string; target: number; triggered?: boolean; active?: boolean; }

function AlertsPanel() {
  const t = useTopic<{ alerts: AlertRow[] }>('alerts:list');
  const alerts = t.data?.alerts ?? [];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PanelTitle icon={Bell} title="Alerts" hint={`${alerts.length} ACTIVE`} />
      {alerts.length === 0 ? <Empty>No active price alerts.</Empty> : (
        <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto scrollbar-hide p-2">
          {alerts.map(a => (
            <div key={a.id} className="flex items-center justify-between rounded-lg border border-border/10 px-2 py-1 text-[11px]">
              <span className="font-mono font-bold text-foreground">{a.symbol}</span>
              <span className="text-muted-foreground">{a.condition}</span>
              <span className="font-mono tabular-nums text-foreground/90">{a.target}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Screener (link out — the full screener is a dedicated page) ──────────────

function ScreenerPanel() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PanelTitle icon={Search} title="Screener" hint="OPEN PAGE" />
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-4 text-center">
        <Search size={20} className="text-muted-foreground/50" />
        <p className="text-[11px] text-muted-foreground">The full screener runs in its own workspace.</p>
        <button
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent('be:navigate', { detail: { tab: 'discovery' } }))}
          className="rounded-lg border border-primary/40 bg-primary/15 px-3 py-1.5 text-[11px] font-bold text-primary hover:bg-primary/25 cursor-pointer"
        >
          Open Market Screener
        </button>
      </div>
    </div>
  );
}

// ── Router ───────────────────────────────────────────────────────────────────

export interface PanelContentProps {
  panel: MarketPanel;
  onPickSymbol?: (symbol: string, market?: string) => void;
}

export function PanelContent({ panel, onPickSymbol }: PanelContentProps) {
  const symbol = panel.symbol ?? panel.chart?.symbol ?? 'AAPL';
  const market = panel.market ?? panel.chart?.market ?? 'US';

  switch (panel.type) {
    case 'watchlist':
      return <WatchlistPanel onPick={onPickSymbol} />;
    case 'market-overview':
      return <MarketOverviewPanel />;
    case 'news':
      return <NewsPanel symbol={symbol} />;
    case 'fundamentals':
      return <FundamentalsPanel symbol={symbol} market={market} />;
    case 'economic-calendar':
      return <EconomicCalendarPanel />;
    case 'ai-analysis':
      return <AiPanel symbol={symbol} market={market} timeframe={panel.chart?.timeframe ?? '1D'} />;
    case 'portfolio':
      return <PortfolioPanel />;
    case 'heatmap':
      return (
        <div className="flex min-h-0 flex-1 flex-col">
          <PanelTitle icon={Layers} title="Market Heatmap" hint="TREEMAP" />
          <div className="min-h-0 flex-1"><MarketHeatmapWidget placement={{ id: panel.id, widgetId: 'market-heatmap', height: null }} /></div>
        </div>
      );
    case 'alerts':
      return <AlertsPanel />;
    case 'screener':
      return <ScreenerPanel />;
    default:
      return <Unavailable label={`panel type "${panel.type}"`} />;
  }
}

export type { MarketPanel };
