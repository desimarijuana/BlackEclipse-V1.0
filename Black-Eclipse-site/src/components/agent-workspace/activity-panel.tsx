'use client';

// ── Agent Workspace — Activity timeline ──────────────────────────────────────
// A chronological, searchable, filterable list of everything the agent did.
// Rows expand for the safe technical detail (operation, path, code, duration) —
// never raw output, memory text or hidden reasoning.
//
// Performance: the list is windowed (renders a slice around the viewport), so a
// run with thousands of activities stays smooth without a virtualization
// dependency.

import { useMemo, useRef, useState } from 'react';
import { Check, ChevronRight, Loader2, Search, XCircle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { ActivityEntry } from '@/lib/agent-workspace/types';
import { formatClock, formatDuration } from '@/lib/agent-workspace/format';
import { CategoryIcon } from './ui';

type Filter = 'all' | 'tools' | 'files' | 'commands' | 'research' | 'errors';

const FILTERS: Array<{ id: Filter; key: 'workspace.filter.all' | 'workspace.filter.tools' | 'workspace.filter.files' | 'workspace.filter.commands' | 'workspace.filter.research' | 'workspace.filter.errors' }> = [
  { id: 'all', key: 'workspace.filter.all' },
  { id: 'tools', key: 'workspace.filter.tools' },
  { id: 'files', key: 'workspace.filter.files' },
  { id: 'commands', key: 'workspace.filter.commands' },
  { id: 'research', key: 'workspace.filter.research' },
  { id: 'errors', key: 'workspace.filter.errors' },
];

const FILTER_MATCH: Record<Filter, (a: ActivityEntry) => boolean> = {
  all: () => true,
  tools: (a) => a.category === 'tool' || a.category === 'command' || a.category === 'git' || a.category === 'browser' || a.category === 'computer',
  files: (a) => a.category === 'file',
  commands: (a) => a.category === 'command',
  research: (a) => a.category === 'research',
  errors: (a) => a.status === 'failed' || a.category === 'error',
};

const WINDOW = 200;

function matchesQuery(item: ActivityEntry, q: string): boolean {
  if (!q) return true;
  const hay = `${item.label} ${item.name ?? ''} ${item.detail ?? ''} ${item.summary ?? ''}`.toLowerCase();
  return hay.includes(q);
}

export function ActivityPanel({ entries }: { entries: ActivityEntry[] }) {
  const t = useT();
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(WINDOW);
  const listRef = useRef<HTMLDivElement>(null);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entries.filter((a) => FILTER_MATCH[filter](a) && matchesQuery(a, q));
  }, [entries, filter, query]);

  // Reset the window when the query/filter changes.
  const key = `${filter}:${query}`;
  const [lastKey, setLastKey] = useState(key);
  if (key !== lastKey) {
    setLastKey(key);
    setLimit(WINDOW);
  }

  const visible = shown.slice(Math.max(0, shown.length - limit));

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
            className={cn(
              'rounded-lg px-2 py-1 text-[11px] transition-colors',
              filter === f.id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
            )}
          >
            {t(f.key)}
          </button>
        ))}
      </div>

      <label className="flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.03] px-2 py-1.5">
        <Search size={13} className="shrink-0 text-muted-foreground/60" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('workspace.searchActivity')}
          aria-label={t('workspace.searchActivity')}
          className="min-w-0 flex-1 bg-transparent text-[12px] text-foreground outline-none placeholder:text-muted-foreground/50"
        />
      </label>

      <div ref={listRef} className="min-h-0 flex-1 space-y-0.5 overflow-y-auto pr-0.5">
        {shown.length === 0 ? (
          <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>
        ) : (
          <>
            {shown.length > visible.length && (
              <button
                type="button"
                onClick={() => setLimit((v) => v + WINDOW * 2)}
                className="w-full rounded-lg py-1 text-[11px] text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"
              >
                ↑ …
              </button>
            )}
            {visible.map((item) => (
              <ActivityRow key={item.id} item={item} />
            ))}
          </>
        )}
      </div>
      {shown.length > 0 && (
        <p className="shrink-0 px-1 text-[10px] text-muted-foreground/40">
          {visible.length.toLocaleString()} / {shown.length.toLocaleString()} · {t('workspace.panel.activity')}
        </p>
      )}
    </div>
  );
}

function ActivityRow({ item }: { item: ActivityEntry }) {
  const [open, setOpen] = useState(false);
  const running = item.status === 'running';
  const failed = item.status === 'failed';
  const hasDetails = Boolean(item.name || item.code || item.detail || item.durationMs != null);

  return (
    <div className="group/act rounded-lg">
      <button
        type="button"
        onClick={() => hasDetails && setOpen((v) => !v)}
        aria-expanded={hasDetails ? open : undefined}
        disabled={!hasDetails}
        className={cn('flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-[12px]', hasDetails && 'cursor-pointer hover:bg-accent/40')}
      >
        <span className={cn('shrink-0', failed ? 'text-rose-400' : running ? 'text-primary' : 'text-muted-foreground/60')}>
          {running ? <Loader2 size={12} className="animate-spin" /> : failed ? <XCircle size={12} /> : <CategoryIcon category={item.category} size={12} />}
        </span>
        <span className={cn('shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/40')}>{formatClock(item.at)}</span>
        <span className={cn('min-w-0 flex-1 truncate', failed ? 'text-rose-200/90' : 'text-muted-foreground')}>
          <span className="text-foreground/80">{item.label}</span>
          {item.detail && <span className="ml-1.5 font-mono text-[11px] text-muted-foreground/70">{item.detail}</span>}
        </span>
        {item.summary && !running && <span className="shrink-0 text-[10px] text-muted-foreground/50">{item.summary}</span>}
        {item.durationMs != null && !running && (
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/40">{formatDuration(item.durationMs)}</span>
        )}
        {!running && !failed && <Check size={11} className="shrink-0 text-emerald-400/60" />}
        {hasDetails && <ChevronRight size={11} className={cn('shrink-0 text-muted-foreground/30 transition-transform', open && 'rotate-90')} />}
      </button>
      {open && (
        <dl className="ml-6 mt-0.5 space-y-0.5 border-l border-white/10 pb-1 pl-3 font-mono text-[10.5px] text-muted-foreground/70">
          {item.name && <DetailRow label="operation" value={item.name} />}
          {item.category && <DetailRow label="category" value={item.category} />}
          {item.code && <DetailRow label="code" value={item.code} tone="failed" />}
        </dl>
      )}
    </div>
  );
}

function DetailRow({ label, value, tone }: { label: string; value: string; tone?: 'failed' }) {
  return (
    <div className="flex gap-2">
      <dt className="shrink-0 text-muted-foreground/40">{label}</dt>
      <dd className={cn('break-all', tone === 'failed' && 'text-rose-300/90')}>{value}</dd>
    </div>
  );
}
