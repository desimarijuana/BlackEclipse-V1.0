'use client';

// ── PriceRibbon — live, customizable price ticker for the app header ─────────
// A continuously scrolling strip of the user's chosen global instruments (US
// indices, crypto, commodities, FX, or any symbol in JDDS). It sits beside the
// global search trigger and is fed by the SAME data paths the rest of the app
// already uses — no new API, no fabricated data.
//
// Data routing. The configured symbols are split by family:
//   • catalog symbols (commodities `GC=F`, FX `EURUSD=X`) come from the shared
//     `market:commodities` / `market:forex` topics;
//   • everything else (indices, stocks, crypto) comes from a dynamic
//     `/api/quote?symbols=…` topic keyed by the sorted symbol set.
// A symbol the upstream cannot price is simply omitted — never rendered with a
// placeholder.
//
// Presentation. No background: the strip is bare text so it reads as live market
// chrome, not a card. Motion is left→right (the loop restarts invisibly with two
// copies of the list) and pauses on hover; it is disabled under
// `prefers-reduced-motion`. Clicking a quote opens it on the chart; the trailing
// gear opens the customization popover.

import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { RotateCcw, Search, Settings2, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { registerTopic, jsonTopic, useTopic } from '@/lib/workspace/data-hub';
import { useCommandStore } from '@/lib/search/store';
import {
  DEFAULT_RIBBON_SYMBOLS,
  RIBBON_MAX_SYMBOLS,
  ribbonLabel,
  splitRibbonSymbols,
  useRibbonSymbols,
} from '@/lib/ribbon/store';

// Idempotent registrations shared with the dashboard registry (identical
// ttl/interval, so the hub ignores the duplicate).
registerTopic(jsonTopic('market:indices:US', '/api/indices?market=US', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:indices:CRYPTO', '/api/indices?market=CRYPTO', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:commodities', '/api/commodities', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:forex', '/api/forex', { ttl: 120_000, interval: 60_000 }));

interface RibbonQuote {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  /** Currency code for display, when known (indices/stocks carry their own). */
  currency?: string;
}

interface IndexRow { symbol: string; name: string; price: number; changePercent: number; currency?: string }
interface ForexRow { symbol: string; name: string; price: number; changePct: number; found: boolean }
interface CommodityRow { symbol: string; name: string; price: number; changePct: number; found: boolean }
interface QuoteRow { symbol: string; name: string; price: number; changePercent: number; currency: string; found: boolean }

/** FX pairs keep 4 decimals with no symbol; everything else is 2 (or sub-unit). */
function formatPrice(symbol: string, price: number): string {
  if (symbol.endsWith('=X')) {
    return price.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  }
  const prefix = symbol.endsWith('=F') || symbol.endsWith('-USD') ? '$' : '';
  const formatted = Math.abs(price) >= 1
    ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
  return `${prefix}${formatted}`;
}

function RibbonItem({ quote, interactive = true }: { quote: RibbonQuote; interactive?: boolean }) {
  const up = quote.changePercent >= 0;
  const open = () => useCommandStore.getState().dispatch({ tab: 'chart', params: { symbol: quote.symbol } });
  const content = (
    <>
      <span className="font-mono text-[11px] font-bold uppercase tracking-wide text-muted-foreground/70 group-hover/item:text-foreground transition-colors">
        {ribbonLabel(quote.symbol)}
      </span>
      <span className="font-mono text-xs font-semibold text-foreground/90">{formatPrice(quote.symbol, quote.price)}</span>
      <span className={cn('font-mono text-[11px] font-semibold', up ? 'text-emerald-400' : 'text-rose-400')}>
        {up ? '+' : ''}{quote.changePercent.toFixed(2)}%
      </span>
    </>
  );
  const className = 'group/item flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1 transition-colors';
  // The second marquee copy is a visual duplicate for the seamless loop, so it is
  // inert: no button, no focus target, hidden from assistive tech.
  if (!interactive) {
    return <span className={cn(className, 'cursor-default')} aria-hidden>{content}</span>;
  }
  return (
    <button onClick={open} title={`${quote.name} — open on chart`} className={cn(className, 'cursor-pointer hover:bg-white/[0.06]')}>
      {content}
    </button>
  );
}

// ── Customization popover ───────────────────────────────────────────────────

interface Suggestion { symbol: string; name: string; marketId?: string; price?: number }

/**
 * Popover for adding/removing ribbon symbols. Anchored under the gear button,
 * portaled to <body> so the frosted panel samples the real page (glass hard
 * rule #3). Autocomplete is the same database search the pin inputs use.
 */
function RibbonConfig({ onClose }: { onClose: () => void }) {
  const { symbols, add, remove, reset } = useRibbonSymbols();
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 1) { setSuggestions([]); return; }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/quote?q=${encodeURIComponent(q)}`);
        const d = await r.json();
        if (cancelled) return;
        setSuggestions((d.suggestions ?? []).filter((s: Suggestion) => !symbols.includes(s.symbol.toUpperCase())));
      } catch { if (!cancelled) setSuggestions([]); }
    }, 200);
    return () => { cancelled = true; clearTimeout(t); };
  }, [query, symbols]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const commit = (s: string) => { add(s); setQuery(''); setSuggestions([]); };
  const atCap = symbols.length >= RIBBON_MAX_SYMBOLS;

  const panel = (
    <div className="fixed inset-0 z-50 flex justify-end" data-keyboard-overlay="true">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className="relative m-3 ml-auto flex h-fit max-h-[80vh] w-80 max-w-[90vw] flex-col self-start rounded-2xl border border-white/10 glass-card-strong text-foreground shadow-2xl">
        <div className="flex items-center justify-between border-b border-border/10 px-4 py-3">
          <span className="font-serif text-sm font-semibold">Customize price ribbon</span>
          <button onClick={onClose} className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer" title="Close">
            <X size={14} />
          </button>
        </div>

        <div className="flex flex-col gap-3 overflow-y-auto scrollbar-hide p-4">
          <p className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground/70">
            Showing {symbols.length}/{RIBBON_MAX_SYMBOLS} · drag-free, add any symbol
          </p>

          {symbols.length === 0 ? (
            <p className="text-xs italic text-muted-foreground/70">No symbols — add some below.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {symbols.map(sym => (
                <span key={sym} className="inline-flex items-center gap-1 rounded-full border border-border/40 bg-accent/40 pl-2 pr-1 py-0.5 text-[10px] font-mono font-bold">
                  {ribbonLabel(sym)}
                  <button
                    onClick={() => remove(sym)}
                    className="text-muted-foreground transition-colors hover:text-rose-400 cursor-pointer leading-none"
                    title={`Remove ${sym}`}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
            <input
              autoFocus
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); if (suggestions[0]) commit(suggestions[0].symbol); else if (query.trim()) commit(query.trim().toUpperCase()); }
              }}
              placeholder={atCap ? 'Ribbon is full' : 'Add any symbol — AAPL, OGDC, BTC…'}
              disabled={atCap}
              className="w-full rounded-lg border border-border/30 bg-background/60 py-1.5 pl-7 pr-2 text-xs font-mono text-foreground outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
            />
          </div>

          {suggestions.length > 0 && (
            <div className="flex max-h-44 flex-col gap-0.5 overflow-y-auto">
              <p className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground/70">Matches — click to add</p>
              {suggestions.slice(0, 50).map(s => (
                <button
                  key={`${s.symbol}-${s.marketId ?? ''}`}
                  onClick={() => commit(s.symbol)}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border/30 px-2.5 py-1.5 text-left transition-colors hover:border-primary/40 hover:bg-primary/10 cursor-pointer"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="font-mono text-[11px] font-bold text-foreground/80">{s.symbol}</span>
                    <span className="truncate text-[11px] text-muted-foreground">{s.name}</span>
                  </span>
                  {s.marketId && <span className="shrink-0 font-mono text-[9px] text-muted-foreground/70">{s.marketId}</span>}
                </button>
              ))}
            </div>
          )}

          {query.length === 0 && (
            <p className="text-[10px] leading-relaxed text-muted-foreground/70">
              Prices are live and refresh automatically. Symbols with no available quote are
              hidden until data arrives — never shown as a fake zero.
            </p>
          )}

          <button
            onClick={reset}
            className="mt-1 inline-flex items-center justify-center gap-1.5 rounded-lg border border-border/40 px-2.5 py-1.5 text-[11px] font-semibold text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50 cursor-pointer"
            title={`Restore the default selection (${DEFAULT_RIBBON_SYMBOLS.length} symbols)`}
          >
            <RotateCcw size={12} /> Reset to defaults
          </button>
        </div>
      </aside>
    </div>
  );

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted ? createPortal(panel, document.body) : null;
}

// ── Ribbon ──────────────────────────────────────────────────────────────────

export function PriceRibbon({ className }: { className?: string }) {
  const { symbols } = useRibbonSymbols();
  const [configOpen, setConfigOpen] = useState(false);

  // Catalog symbols (commodities/FX) come from their dedicated topics; only the
  // remaining symbols are sent to /api/quote.
  const quoteSymbols = useMemo(() => splitRibbonSymbols(symbols).quotes, [symbols]);

  // Dynamic topic for the non-catalog symbols (indices/stocks/crypto). Keyed by
  // the sorted set so two viewers with the same list share one poll.
  const quoteKey = useMemo(() => [...new Set(quoteSymbols)].sort().join(','), [quoteSymbols]);
  const quoteTopicId = quoteKey ? `ribbon:quote:${quoteKey}` : 'ribbon:quote:__empty__';
  useMemo(() => {
    if (!quoteKey) return;
    registerTopic(jsonTopic(quoteTopicId, `/api/quote?symbols=${encodeURIComponent(quoteKey)}`, { ttl: 60_000, interval: 30_000 }));
  }, [quoteTopicId, quoteKey]);

  const quotes = useTopic<{ quotes?: QuoteRow[] }>(quoteTopicId);
  const commodities = useTopic<{ commodities?: CommodityRow[] }>('market:commodities');
  const forex = useTopic<{ pairs?: ForexRow[] }>('market:forex');
  // Index name/currency enrichment comes from the shared index topics.
  const indices = useTopic<{ indices?: IndexRow[] }>('market:indices:US');

  const quotesBySymbol = useMemo(() => {
    const map = new Map<string, RibbonQuote>();
    const put = (symbol: string, name: string, price: number, changePercent: number, currency?: string) => {
      const key = symbol.toUpperCase();
      if (!(price > 0) || map.has(key)) return;
      map.set(key, { symbol: key, name, price, changePercent, currency });
    };
    for (const r of quotes.data?.quotes ?? []) { if (r.found) put(r.symbol, r.name, r.price, r.changePercent, r.currency); }
    for (const r of indices.data?.indices ?? []) put(r.symbol, r.name, r.price, r.changePercent, r.currency);
    for (const c of commodities.data?.commodities ?? []) { if (c.found) put(c.symbol, c.name, c.price, c.changePct); }
    for (const p of forex.data?.pairs ?? []) { if (p.found) put(p.symbol, p.name, p.price, p.changePct); }
    return map;
  }, [quotes.data, indices.data, commodities.data, forex.data]);

  // Preserve the user's chosen order; omit anything not yet priced.
  const rows = useMemo(
    () => symbols.map(s => quotesBySymbol.get(s.toUpperCase())).filter((q): q is RibbonQuote => q !== undefined),
    [symbols, quotesBySymbol],
  );

  const gear = (
    <button
      onClick={() => setConfigOpen(true)}
      className="pointer-events-auto ml-1 grid h-6 w-6 shrink-0 place-items-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-white/[0.08] hover:text-foreground cursor-pointer"
      title="Customize the price ribbon"
    >
      <Settings2 size={13} />
    </button>
  );

  if (rows.length === 0) {
    return (
      <div className={cn('hidden min-w-0 flex-1 items-center gap-1 lg:flex', className)}>
        <span className="truncate font-mono text-[11px] uppercase tracking-wide text-muted-foreground/50">Live prices unavailable</span>
        {gear}
        {configOpen && <RibbonConfig onClose={() => setConfigOpen(false)} />}
      </div>
    );
  }

  return (
    <div className={cn('group/ribbon hidden min-w-0 flex-1 items-center lg:flex', className)}>
      {/* Mask fades the quotes into the header at both edges (no background). */}
      <div
        className="price-ribbon min-w-0 flex-1 overflow-hidden"
        title="Live global prices — click a quote to open it on the chart"
      >
        {/* Two identical copies; the marquee loops left→right with no visible jump. */}
        <div className="price-ribbon-track flex items-center">
          {[0, 1].map(copy => (
            <div key={copy} className="flex items-center">
              {rows.map(q => <RibbonItem key={`${copy}-${q.symbol}`} quote={q} interactive={copy === 0} />)}
            </div>
          ))}
        </div>
      </div>
      {gear}
      {configOpen && <RibbonConfig onClose={() => setConfigOpen(false)} />}
    </div>
  );
}
