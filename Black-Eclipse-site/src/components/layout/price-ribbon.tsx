'use client';

// ── PriceRibbon — live global price ticker for the app header ────────────────
// A compact, continuously scrolling strip of the key global instruments (US
// indices, crypto majors, commodities, FX majors). It sits next to the global
// search trigger and is fed by the SAME DataHub topics the dashboard and
// screener already use — no extra polling, no second cache, no fabricated data.
//
// Provenance: every row comes from one of four server-cached topics
// (`market:indices:US`, `market:indices:CRYPTO`, `market:commodities`,
// `market:forex`). A symbol the upstream doesn't return is simply omitted —
// never rendered with a placeholder price.
//
// Clicking a row opens it on the chart tab via the command-center destination
// bus (`useCommandStore.dispatch`), matching how every other cross-screen
// navigation works.

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { registerTopic, jsonTopic, useTopic } from '@/lib/workspace/data-hub';
import { useCommandStore } from '@/lib/search/store';

// Idempotent registrations. The dashboard registry uses identical ttl/interval
// values, so whichever module loads first wins and the hub ignores the rest.
registerTopic(jsonTopic('market:indices:US', '/api/indices?market=US', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:indices:CRYPTO', '/api/indices?market=CRYPTO', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:commodities', '/api/commodities', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:forex', '/api/forex', { ttl: 120_000, interval: 60_000 }));

interface RibbonQuote {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
}

/** Curated ribbon composition, in display order. */
const RIBBON_ORDER: string[] = [
  '^GSPC', '^IXIC', '^DJI',
  'BTC-USD', 'ETH-USD',
  'GC=F', 'CL=F',
  'EURUSD=X', 'USDJPY=X', 'GBPUSD=X',
];

/** Indices payload row (indices + sector topics share the shape prefix). */
interface IndexRow { symbol: string; name: string; price: number; changePercent: number }
interface ForexRow { symbol: string; name: string; price: number; changePct: number; found: boolean }
interface CommodityRow { symbol: string; name: string; price: number; changePct: number; found: boolean }

/**
 * Format a ribbon price for its instrument class: FX pairs keep 4 decimals and
 * carry no currency symbol, crypto/commodities are dollar-quoted, and index
 * levels are plain grouped numbers.
 */
function formatRibbonPrice(symbol: string, price: number): string {
  if (symbol.endsWith('=X')) {
    return price.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  }
  const prefix = symbol.endsWith('=F') || symbol.endsWith('-USD') ? '$' : '';
  const formatted =
    Math.abs(price) >= 1
      ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
  return `${prefix}${formatted}`;
}

/** Display ticker: drop the Yahoo decorations (^GSPC → GSPC, BTC-USD → BTC). */
function ribbonLabel(symbol: string): string {
  return symbol.replace(/^\^/, '').replace(/-USD$/, '').replace(/=.$/, '');
}

function RibbonItem({ quote, interactive = true }: { quote: RibbonQuote; interactive?: boolean }) {
  const up = quote.changePercent >= 0;
  const open = () => useCommandStore.getState().dispatch({ tab: 'chart', params: { symbol: quote.symbol } });
  const content = (
    <>
      <span className="font-mono text-[10px] font-bold uppercase tracking-wide text-muted-foreground/70 group-hover/item:text-foreground transition-colors">
        {ribbonLabel(quote.symbol)}
      </span>
      <span className="font-mono text-[11px] font-semibold text-foreground/90">{formatRibbonPrice(quote.symbol, quote.price)}</span>
      <span className={cn('font-mono text-[10px] font-semibold', up ? 'text-emerald-400' : 'text-rose-400')}>
        {up ? '+' : ''}{quote.changePercent.toFixed(2)}%
      </span>
    </>
  );
  const className = 'group/item flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 transition-colors';
  // The second marquee copy is a visual duplicate for the seamless loop, so it
  // is inert: no button, no focus target, hidden from assistive tech.
  if (!interactive) {
    return <span className={cn(className, 'px-2 py-1')} aria-hidden>{content}</span>;
  }
  return (
    <button onClick={open} title={`${quote.name} — open on chart`} className={cn(className, 'cursor-pointer hover:bg-white/[0.06]')}>
      {content}
    </button>
  );
}

export function PriceRibbon({ className }: { className?: string }) {
  const indices = useTopic<{ indices?: IndexRow[] }>('market:indices:US');
  const crypto = useTopic<{ indices?: IndexRow[] }>('market:indices:CRYPTO');
  const commodities = useTopic<{ commodities?: CommodityRow[] }>('market:commodities');
  const forex = useTopic<{ pairs?: ForexRow[] }>('market:forex');

  const quotes = useMemo(() => {
    const bySymbol = new Map<string, RibbonQuote>();
    const put = (symbol: string, name: string, price: number, changePercent: number) => {
      if (!(price > 0) || bySymbol.has(symbol.toUpperCase())) return;
      bySymbol.set(symbol.toUpperCase(), { symbol, name, price, changePercent });
    };
    for (const r of indices.data?.indices ?? []) put(r.symbol, r.name, r.price, r.changePercent);
    for (const r of crypto.data?.indices ?? []) put(r.symbol, r.name, r.price, r.changePercent);
    for (const c of commodities.data?.commodities ?? []) { if (c.found) put(c.symbol, c.name, c.price, c.changePct); }
    for (const p of forex.data?.pairs ?? []) { if (p.found) put(p.symbol, p.name, p.price, p.changePct); }
    return RIBBON_ORDER.map((s) => bySymbol.get(s)).filter((q): q is RibbonQuote => q !== undefined);
  }, [indices.data, crypto.data, commodities.data, forex.data]);

  if (quotes.length === 0) {
    return (
      <div className={cn('glass-card-subtle hidden h-9 items-center rounded-xl border border-border/40 px-3 lg:flex', className)}>
        <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground/50">Live prices unavailable</span>
      </div>
    );
  }

  return (
    <div
      className={cn('price-ribbon glass-card-subtle hidden h-9 items-center overflow-hidden rounded-xl border border-border/40 lg:flex', className)}
      title="Live global prices — click a quote to open it on the chart"
    >
      {/* Two identical tracks; the marquee translates -50% for a seamless loop.
          The glass surface is the untransformed wrapper so the backdrop blur is
          never scoped to a transformed ancestor (see globals.css hard rules). */}
      <div className="price-ribbon-track flex items-center">
        {[0, 1].map((copy) => (
          <div key={copy} className="flex items-center">
            {quotes.map((q) => <RibbonItem key={`${copy}-${q.symbol}`} quote={q} interactive={copy === 0} />)}
          </div>
        ))}
      </div>
    </div>
  );
}
