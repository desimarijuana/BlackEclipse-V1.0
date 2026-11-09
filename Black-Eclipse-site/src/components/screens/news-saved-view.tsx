'use client';

// ─── Saved news view ────────────────────────────────────────────────────────
// The Saved tab is its own searchable, filterable, paginated list (not a
// filter over the current feed page). It reads the snapshots persisted by
// `lib/news/saved.ts`, so bookmarks survive feed refreshes and page changes.

import { useMemo, useState } from 'react';
import { Bookmark, Search, Sparkles, X } from '@/lib/icons';
import { PageSizeInput } from '@/components/ui/pagination';
import { relativeTime } from '@/lib/news/relative-time';
import type { NewsItem } from '@/components/screens/market-news';

type Sentiment = 'all' | NewsItem['sentiment'];
type Sort = 'newest' | 'oldest';

const SENTIMENTS: Array<{ value: Sentiment; label: string }> = [
  { value: 'all', label: 'Any sentiment' },
  { value: 'bullish', label: 'Bullish' },
  { value: 'bearish', label: 'Bearish' },
  { value: 'neutral', label: 'Neutral' },
];

export function NewsSavedView({
  items,
  onOpen,
  onRemove,
  onDiscuss,
  onBack,
}: {
  items: NewsItem[];
  onOpen: (item: NewsItem) => void;
  onRemove: (item: NewsItem) => void;
  onDiscuss: (item: NewsItem) => void;
  onBack: () => void;
}) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [sentiment, setSentiment] = useState<Sentiment>('all');
  const [sort, setSort] = useState<Sort>('newest');
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);

  const categories = useMemo(
    () => [...new Set(items.map((i) => i.category).filter((c): c is string => Boolean(c)))].sort(),
    [items],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = items.filter((item) => {
      if (category && item.category !== category) return false;
      if (sentiment !== 'all' && item.sentiment !== sentiment) return false;
      if (!q) return true;
      return [item.headline, item.summary, item.source, item.ticker]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(q));
    });
    return rows.sort((a, b) => {
      const d = Date.parse(a.timestamp) - Date.parse(b.timestamp);
      return sort === 'newest' ? -d : d;
    });
  }, [items, query, category, sentiment, sort]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const pageItems = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  const reset = (fn: () => void) => { fn(); setPage(1); };

  return (
    <div className="w-full flex flex-col gap-4">
      <div className="w-full rounded-2xl border border-border/10 glass-card p-4 flex flex-col lg:flex-row lg:items-center gap-3">
        <div className="relative flex-1 min-w-0">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => reset(() => setQuery(e.target.value))}
            placeholder="Search saved articles…"
            className="h-9 w-full rounded-lg bg-accent/30 border border-border/30 pl-9 pr-8 text-[12px] font-mono text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/60"
          />
          {query && (
            <button type="button" onClick={() => reset(() => setQuery(''))}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer" aria-label="Clear search">
              <X size={13} />
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={category} onChange={(e) => reset(() => setCategory(e.target.value))}
            className="h-9 rounded-lg bg-accent/30 border border-border/30 px-3 text-[12px] font-mono text-foreground cursor-pointer focus:outline-none focus:border-primary/60">
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={sentiment} onChange={(e) => reset(() => setSentiment(e.target.value as Sentiment))}
            className="h-9 rounded-lg bg-accent/30 border border-border/30 px-3 text-[12px] font-mono text-foreground cursor-pointer focus:outline-none focus:border-primary/60">
            {SENTIMENTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <select value={sort} onChange={(e) => reset(() => setSort(e.target.value as Sort))}
            className="h-9 rounded-lg bg-accent/30 border border-border/30 px-3 text-[12px] font-mono text-foreground cursor-pointer focus:outline-none focus:border-primary/60">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
          <button type="button" onClick={onBack}
            className="h-9 px-3 rounded-lg bg-accent/30 border border-border/30 text-[12px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer">
            Back to feed
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between px-1 font-mono text-[11px] text-muted-foreground flex-wrap gap-2">
        <span><span className="text-foreground font-bold">{filtered.length}</span> saved article{filtered.length === 1 ? '' : 's'}</span>
        <PageSizeInput pageSize={pageSize} max={200} onCommit={(n) => { setPageSize(n); setPage(1); }} />
      </div>

      {filtered.length === 0 ? (
        <div className="w-full text-center py-12 font-mono text-xs text-muted-foreground border border-dashed border-border/25 rounded-2xl glass-card-subtle">
          <Bookmark size={20} className="mx-auto mb-2 text-muted-foreground/60" />
          {items.length === 0
            ? 'No saved articles yet — tap the ribbon icon on any news card.'
            : 'No saved articles match these filters.'}
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {pageItems.map((item) => (
            <div key={item.id}
              className="rounded-xl border border-border/20 glass-card-subtle p-3.5 flex flex-col gap-2 hover:border-primary/30 transition-colors">
              <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono">
                <span className="font-bold uppercase text-muted-foreground bg-accent/60 px-2 py-0.5 rounded border border-border/40">{item.source}</span>
                {item.category && <span className="text-primary/80 uppercase bg-primary/5 border border-primary/15 px-2 py-0.5 rounded">{item.category}</span>}
                {item.ticker && <span className="font-extrabold text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded">{item.ticker}</span>}
                <span className={`px-2 py-0.5 rounded-full border uppercase tracking-wider ${
                  item.sentiment === 'bullish' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : item.sentiment === 'bearish' ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                      : 'bg-neutral-500/10 text-neutral-400 border-neutral-500/30'
                }`}>{item.sentiment}</span>
                <span className="text-muted-foreground/70">{relativeTime(item.timestamp)}</span>
              </div>
              <button type="button" onClick={() => onOpen(item)}
                className="text-left text-sm font-semibold text-foreground hover:text-primary transition-colors cursor-pointer">
                {item.headline}
              </button>
              {item.summary && <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">{item.summary}</p>}
              <div className="flex items-center gap-2 pt-1">
                <button type="button" onClick={() => onRemove(item)}
                  className="h-7 px-2.5 rounded-lg border border-amber-400/40 bg-amber-400/10 text-amber-400 text-[10px] font-bold inline-flex items-center gap-1.5 cursor-pointer"
                  title="Remove bookmark">
                  <Bookmark size={11} weight="fill" /> Saved
                </button>
                <button type="button" onClick={() => onDiscuss(item)}
                  className="h-7 px-2.5 rounded-lg border border-primary/20 bg-primary/10 text-primary text-[10px] font-bold inline-flex items-center gap-1.5 cursor-pointer">
                  <Sparkles size={11} /> Discuss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {filtered.length > 0 && pageCount > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/10 glass-card-subtle p-3 font-mono text-[11px]">
          <span className="text-muted-foreground">
            Page <span className="text-foreground font-bold">{safePage}</span> of <span className="text-foreground font-bold">{pageCount}</span>
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            <button type="button" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}
              className="h-8 px-2.5 rounded-lg border border-border/30 bg-accent/30 text-muted-foreground disabled:opacity-30 cursor-pointer">Prev</button>
            {Array.from({ length: pageCount }).slice(
              Math.max(0, safePage - 3),
              Math.max(0, safePage - 3) + 5,
            ).map((_, idx) => {
              const n = Math.max(0, safePage - 3) + idx + 1;
              return (
                <button key={n} type="button" onClick={() => setPage(n)}
                  className={`h-8 min-w-[32px] rounded-lg border text-[11px] font-bold cursor-pointer ${
                    n === safePage ? 'bg-primary/15 text-primary border-primary/40' : 'bg-accent/30 text-muted-foreground border-border/30'
                  }`}>
                  {n}
                </button>
              );
            })}
            <button type="button" disabled={safePage >= pageCount} onClick={() => setPage(safePage + 1)}
              className="h-8 px-2.5 rounded-lg border border-border/30 bg-accent/30 text-muted-foreground disabled:opacity-30 cursor-pointer">Next</button>
          </div>
        </div>
      )}
    </div>
  );
}
