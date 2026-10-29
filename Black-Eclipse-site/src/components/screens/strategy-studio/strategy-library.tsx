'use client';

// ── Strategy library ────────────────────────────────────────────────────────
// The studio used to show nothing you had already built, so a refresh stranded
// your work. This rail lists the saved strategies from the quant store and
// opens one back into the editor.

import React, { useMemo, useState } from 'react';
import { BookOpen, Loader2, Plus, Search } from '@/lib/icons';
import type { StrategySummary } from '@/lib/backtest/backtest-client';
import { cn } from '@/lib/utils';

function when(value?: string | null): string {
  if (!value) return '';
  return value.slice(0, 10);
}

export function StrategyLibrary({
  strategies,
  templates,
  loading,
  selectedId,
  busy = false,
  onOpen,
  onNew,
  onTemplate,
}: {
  strategies: StrategySummary[];
  templates: Array<{ id: string; name: string; tagline: string }>;
  loading: boolean;
  selectedId: string | null;
  busy?: boolean;
  onOpen: (id: string) => void;
  onNew: () => void;
  onTemplate: (id: string) => void;
}) {
  const [query, setQuery] = useState('');

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const sorted = [...strategies].sort((a, b) => (b.updatedAt ?? '').localeCompare(a.updatedAt ?? ''));
    if (!needle) return sorted;
    return sorted.filter((item) =>
      [item.id, item.name, item.description ?? ''].some((field) => field.toLowerCase().includes(needle)),
    );
  }, [strategies, query]);

  return (
    <section className="glass-card rounded-2xl p-4" aria-label="Saved strategies">
      <div className="mb-2 flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Saved strategies</h2>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {loading ? 'loading…' : `${strategies.length}`}
        </span>
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

      <div className="mt-2 max-h-[220px] space-y-0.5 overflow-y-auto scrollbar-hide">
        {!loading && visible.length === 0 ? (
          <p className="px-1 py-2 text-[11px] leading-relaxed text-muted-foreground">
            {strategies.length === 0
              ? 'Nothing saved yet. Draft one below — it will appear here once you save and run it.'
              : 'No strategy matches that search.'}
          </p>
        ) : null}

        {visible.map((item) => {
          const active = item.id === selectedId;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onOpen(item.id)}
              disabled={busy}
              aria-current={active ? 'true' : undefined}
              className={cn(
                'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition disabled:opacity-50',
                active ? 'bg-primary/15 ring-1 ring-primary/30' : 'hover:bg-white/5',
              )}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[11px] text-foreground">{item.name || item.id}</span>
                <span className="block truncate font-mono text-[9px] text-muted-foreground">
                  {item.id} · v{item.latestVersion}
                  {item.updatedAt ? ` · ${when(item.updatedAt)}` : ''}
                </span>
              </span>
              {busy && active ? <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" /> : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
