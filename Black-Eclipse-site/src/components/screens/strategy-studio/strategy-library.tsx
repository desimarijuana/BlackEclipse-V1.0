'use client';

// ── Strategy library ────────────────────────────────────────────────────────
// One rail, always fresh: every strategy (agent-made or hand-authored) with the
// evidence needed to choose one — its newest backtest, approval and paper run.
// Refresh is explicit AND automatic (focus, tab visible, agent turn finished).

import React, { useMemo, useState } from 'react';
import { BookOpen, Loader2, Plus, RefreshCw, Search } from '@/lib/icons';
import { isBacktestComplete, sortStrategies, useStrategyCatalog } from '@/lib/strategies/catalog';
import { cn } from '@/lib/utils';

function when(value?: string | null): string {
  if (!value) return '';
  return value.slice(0, 10);
}

export function backtestLabel(item: { latestBacktest?: { status: string } | null }): {
  text: string;
  tone: string;
} {
  const status = item.latestBacktest?.status;
  if (!status) return { text: 'no backtest', tone: 'text-amber-300/80' };
  if (isBacktestComplete(status)) return { text: 'backtest ✓', tone: 'text-emerald-300/90' };
  return { text: `backtest ${status}`, tone: 'text-amber-300/90' };
}

export function StrategyLibrary({
  templates,
  selectedId,
  busy = false,
  onOpen,
  onNew,
  onTemplate,
}: {
  templates: Array<{ id: string; name: string; tagline: string }>;
  selectedId: string | null;
  busy?: boolean;
  onOpen: (id: string) => void;
  onNew: () => void;
  onTemplate: (id: string) => void;
}) {
  const catalog = useStrategyCatalog();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<'updated' | 'name'>('updated');

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const sorted = sortStrategies(catalog.items, sort);
    if (!needle) return sorted;
    return sorted.filter((item) =>
      [item.id, item.name, item.description ?? ''].some((field) =>
        field.toLowerCase().includes(needle),
      ),
    );
  }, [catalog.items, query, sort]);

  return (
    <section className="glass-card rounded-2xl p-4" aria-label="Saved strategies">
      <div className="mb-2 flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Saved strategies</h2>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {catalog.loading ? 'loading…' : `${catalog.items.length}`}
        </span>
        <button
          type="button"
          onClick={catalog.refresh}
          disabled={catalog.loading}
          title="Refresh the strategy library"
          aria-label="Refresh strategies"
          className="rounded-lg p-1 text-muted-foreground hover:bg-white/5 hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw className={cn('h-3 w-3', catalog.loading && 'animate-spin')} />
        </button>
        <button
          type="button"
          onClick={onNew}
          className="glass-button flex items-center gap-1 rounded-lg px-2 py-1 text-[10px]"
          title="Start a new strategy in this workspace"
        >
          <Plus className="h-3 w-3" /> New
        </button>
      </div>

      <label className="relative block">
        <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name or id"
          aria-label="Search saved strategies"
          className="w-full rounded-lg border border-white/10 bg-black/25 py-1.5 pl-7 pr-2 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/40"
        />
      </label>

      <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
        <label className="inline-flex cursor-pointer items-center gap-1.5">
          <input
            type="checkbox"
            checked={catalog.includeArchived}
            onChange={(event) => catalog.setIncludeArchived(event.target.checked)}
          />
          Show archived
        </label>
        <select
          value={sort}
          onChange={(event) => setSort(event.target.value as 'updated' | 'name')}
          aria-label="Sort saved strategies"
          className="rounded border border-white/10 bg-black/25 px-1 py-0.5 text-[10px] text-foreground outline-none"
        >
          <option value="updated">Newest first</option>
          <option value="name">Name A–Z</option>
        </select>
        {catalog.updatedAt ? (
          <span title="Last refreshed">updated {new Date(catalog.updatedAt).toLocaleTimeString()}</span>
        ) : null}
      </div>

      {catalog.error && (
        <div className="mt-2 rounded-lg border border-rose-500/25 bg-rose-500/5 px-2 py-1.5 text-[10px] text-rose-200">
          {catalog.error}{' '}
          <button type="button" onClick={catalog.refresh} className="underline">
            Retry
          </button>
        </div>
      )}

      <details className="mt-2 text-[11px] text-muted-foreground">
        <summary className="cursor-pointer select-none">Start from a template</summary>
        <div className="mt-1 grid gap-1">
          {templates.map((template) => (
            <button
              key={template.id}
              type="button"
              onClick={() => onTemplate(template.id)}
              disabled={busy}
              title={template.tagline}
              className="rounded-lg border border-white/10 px-2 py-1 text-left transition hover:bg-white/5 disabled:opacity-50"
            >
              <span className="block text-[10px] text-foreground">{template.name}</span>
              <span className="block text-[9px] leading-tight text-muted-foreground">{template.tagline}</span>
            </button>
          ))}
        </div>
        <p className="mt-1 text-[9px] leading-relaxed text-muted-foreground/60">
          Templates are examples, not recommendations.
        </p>
      </details>

      <div className="mt-2 max-h-[260px] space-y-0.5 overflow-y-auto scrollbar-hide">
        {!catalog.loading && visible.length === 0 ? (
          <p className="px-1 py-2 text-[11px] leading-relaxed text-muted-foreground">
            {catalog.items.length === 0
              ? 'Nothing saved yet. Draft one below — it will appear here once you save and run it.'
              : 'No strategy matches that search.'}
          </p>
        ) : null}

        {visible.map((item) => {
          const active = item.id === selectedId;
          const backtest = backtestLabel(item);
          const approved = item.approval?.status === 'approved';
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onOpen(item.id)}
              disabled={busy}
              aria-current={active ? 'true' : undefined}
              className={cn(
                'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition disabled:opacity-50',
                active ? 'bg-primary/15 ring-1 ring-primary/30' : 'hover:bg-white/5',
              )}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[11px] text-foreground">
                  {item.name || item.id}
                  {item.archived ? (
                    <span className="ml-1 rounded bg-white/10 px-1 text-[9px] uppercase text-muted-foreground">
                      archived
                    </span>
                  ) : null}
                </span>
                <span className="block truncate font-mono text-[9px] text-muted-foreground">
                  {item.id} · v{item.latestVersion}
                  {item.updatedAt ? ` · ${when(item.updatedAt)}` : ''}
                </span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px]">
                  <span className={backtest.tone}>{backtest.text}</span>
                  {approved ? <span className="text-emerald-300/90">approved</span> : null}
                  {item.lastPaperRun ? <span className="text-sky-300/80">paper ✓</span> : null}
                </span>
              </span>
              {busy && active ? <Loader2 className="mt-0.5 h-3 w-3 animate-spin text-muted-foreground" /> : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
