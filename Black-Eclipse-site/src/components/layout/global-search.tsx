// ── GlobalSearch — universal command center ────────────────────────────────
// Linear-style command menu in the Black Eclipse design language: grouped
// sections with icon tiles, inset highlighted rows, breadcrumb subtitles, and
// pinned quick actions at the bottom. Searches pages, indicators, actions, and
// the full JDDS universe (55k+ assets via FlexSearch). Fully offline.

'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot,
  BookOpen,
  Briefcase,
  ChartCandlestick,
  Globe,
  Search,
  CornerDownLeft,
  Plus,
  Loader2,
  X,
  type LucideIcon,
} from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { useCommandStore } from '@/lib/search/store';
import { resolveQuery } from '@/lib/search/resolver';
import { universeCount } from '@/lib/search/universe';
import { useCommandCenterKeybind } from '@/hooks/use-command-center-keybind';
import type { EntityKind } from '@/lib/search/types';

const KIND_ICON: Record<EntityKind, LucideIcon> = {
  security: ChartCandlestick,
  instrument: ChartCandlestick,
  indicator: Globe,
  event: Globe,
  page: BookOpen,
  action: Bot,
  report: BookOpen,
  agent: Bot,
  doc: BookOpen,
  user: Briefcase,
};

const KIND_LABEL: Record<EntityKind, string> = {
  security: 'Instruments',
  instrument: 'Instruments',
  indicator: 'Economic Indicators',
  event: 'Economic Indicators',
  page: 'Navigation',
  action: 'Commands',
  report: 'Reports',
  agent: 'Agents',
  doc: 'Docs',
  user: 'Your data',
};

const SECTION_ORDER: EntityKind[] = [
  'action',
  'page',
  'indicator',
  'event',
  'security',
  'instrument',
  'report',
  'agent',
  'doc',
  'user',
];

interface QuickAction {
  id: string;
  label: string;
  icon: LucideIcon;
  run: () => void;
}

type Row =
  | { type: 'recent'; id: string; text: string; onSelect: () => void; onDelete: () => void }
  | { type: 'result'; id: string; title: string; subtitle: string; kind: EntityKind; onSelect: () => void }
  | { type: 'action'; id: string; label: string; icon: LucideIcon; onSelect: () => void };

interface Section {
  key: string;
  label: string;
  rows: { row: Row; flatIndex: number }[];
}

function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim();
  if (!q) return <>{text}</>;
  const lower = text.toLowerCase();
  const idx = lower.indexOf(q.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-primary/30 text-primary-foreground rounded-[2px] px-px">
        {text.slice(idx, idx + q.length)}
      </mark>
      {text.slice(idx + q.length)}
    </>
  );
}

export function GlobalSearch() {
  const store = useCommandStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [debouncedQuery, setDebouncedQuery] = useState('');

  useCommandCenterKeybind({
    open: store.open,
    onToggle: store.toggle,
    slashShortcut: true,
  });

  // Load the universe index + economic calendar + server-side entities.
  useEffect(() => {
    if (store.open) {
      store.ensureUniverse();
      store.ensureCalendar();
      store.ensureGlobal();
    }
  }, [store.open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Focus input when the overlay opens.
  useEffect(() => {
    if (store.open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [store.open]);

  // Scroll the active row into view so ↑/↓ keeps the highlight visible.
  useEffect(() => {
    const container = resultsRef.current;
    if (!container) return;
    const active = container.querySelector<HTMLElement>('[data-selected="true"]');
    active?.scrollIntoView({ block: 'nearest' });
  }, [store.selectedIndex, store.open]);

  // Debounce the query so heavy resolution (universe fuzzy) doesn't run on
  // every keystroke. 80ms keeps the palette feeling instant.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(store.query), 80);
    return () => clearTimeout(t);
  }, [store.query]);

  // Resolve against the debounced query; re-resolves when the universe,
  // calendar, or server-side entities finish loading.
  const resolved = useMemo(() => {
    const q = debouncedQuery.trim();
    if (!q) return null;
    return resolveQuery(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, store.universeReady, store.calendarReady, store.globalReady]);

  const showRecents = !debouncedQuery.trim();
  const indexCount = universeCount();

  const quickActions: QuickAction[] = useMemo(() => [
    {
      id: 'qa-new-chat',
      label: 'Start new chat',
      icon: Plus,
      run: () => {
        store.dispatch({ tab: 'chat', params: { action: 'new-chat' } });
        useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
      },
    },
    {
      id: 'qa-portfolio',
      label: 'Open Portfolio',
      icon: Briefcase,
      run: () => {
        store.dispatch({ tab: 'portfolio' });
        useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
      },
    },
    {
      id: 'qa-journal',
      label: 'Open Trading Journal',
      icon: BookOpen,
      run: () => {
        store.dispatch({ tab: 'journal' });
        useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
      },
    },
    {
      id: 'qa-events',
      label: "Today's economic events",
      icon: Globe,
      run: () => {
        store.dispatch({ tab: 'economics', subroute: 'economics.calendar' });
        useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
      },
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], []);

  // Build sections + a flat navigable row list.
  const { sections, flatRows } = useMemo(() => {
    const flat: Row[] = [];
    const sections: Section[] = [];

    if (showRecents) {
      if (store.recents.length > 0) {
        const rows = store.recents.map<Row>((r) => ({
          type: 'recent',
          id: 'recent-' + r.ts,
          text: r.text,
          onSelect: () => store.setQuery(r.text),
          onDelete: () => store.removeRecent(r.text),
        }));
        sections.push({
          key: 'recent',
          label: 'Recent searches',
          rows: rows.map((row) => ({ row, flatIndex: flat.push(row) - 1 })),
        });
      }
    } else if (resolved && resolved.items.length > 0) {
      const byKind = new Map<EntityKind, Row[]>();
      resolved.items.forEach((it) => {
        const kind = it.entity.kind;
        const list = byKind.get(kind) ?? [];
        const dest = it.entity.destination;
        list.push({
          type: 'result',
          id: it.entity.id,
          title: it.entity.symbol ? `${it.entity.symbol}  ${it.entity.title}` : it.entity.title,
          subtitle: it.entity.subtitle || KIND_LABEL[kind],
          kind,
          onSelect: () => {
            if (dest) {
              store.dispatch(dest);
              store.recordRecent(store.query);
              useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
            }
          },
        });
        byKind.set(kind, list);
      });
      for (const kind of SECTION_ORDER.filter((k) => byKind.has(k))) {
        const list = byKind.get(kind)!;
        sections.push({
          key: kind,
          label: KIND_LABEL[kind],
          rows: list.map((row) => ({ row, flatIndex: flat.push(row) - 1 })),
        });
      }
    }

    // Pinned quick actions at the bottom (part of the flat list).
    for (const qa of quickActions) {
      flat.push({ type: 'action', id: qa.id, label: qa.label, icon: qa.icon, onSelect: qa.run });
    }

    // AI escalation row — shown for sentence-like questions. Routes the query
    // into the chat tab as a prompt (works with or without an LLM configured).
    if (resolved && resolved.intent === 'ai') {
      const aiRow: Row = {
        type: 'action',
        id: 'ai-ask',
        label: `Ask AI: “${debouncedQuery}”`,
        icon: Bot,
        onSelect: () => {
          store.dispatch({ tab: 'chat', params: { prompt: debouncedQuery } });
          useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
        },
      };
      flat.unshift(aiRow);
    }

    return { sections, flatRows: flat };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, store.recents, store.universeReady, resolved, showRecents, quickActions]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const count = flatRows.length;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      store.setSelectedIndex(count > 0 ? (store.selectedIndex + 1) % count : 0);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      store.setSelectedIndex(count > 0 ? (store.selectedIndex - 1 + count) % count : 0);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const row = flatRows[Math.min(store.selectedIndex, count - 1)];
      if (row) row.onSelect();
      else store.runPrimary();
    }
  };

  return (
    <Dialog open={store.open} onOpenChange={(o) => store.setOpen(o)}>
      <DialogContent
        showCloseButton={false}
        className="command-glass top-0 translate-y-0 left-1/2 -translate-x-1/2 sm:max-w-lg max-w-[calc(100%-1rem)] mt-5 w-full p-0 gap-0 rounded-xl overflow-hidden"
      >
        <DialogTitle className="sr-only">Global Search</DialogTitle>

        {/* Input row */}
        <div className="flex items-center gap-3 px-4 py-3.5">
          <Search size={17} className="text-muted-foreground/70 shrink-0" />
          <input
            ref={inputRef}
            value={store.query}
            onChange={(e) => store.setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search instruments, indicators, pages…"
            className="h-8 flex-1 border-0 bg-transparent outline-none px-0 font-mono text-[15px] text-foreground placeholder:text-muted-foreground/60"
            autoComplete="off"
            spellCheck={false}
          />
          {store.universeLoading && <Loader2 size={14} className="animate-spin text-muted-foreground/60 shrink-0" />}
        </div>

        <div className="h-px bg-border/60" />

        {/* Results */}
        <div ref={resultsRef} className="max-h-[min(50dvh,400px)] overflow-y-auto py-2">
          {showRecents && sections.length === 0 && (
            <div className="px-4 py-8 text-center text-xs text-muted-foreground/60">
              No recent searches yet — try a symbol like{' '}
              <span className="font-mono text-primary">AAPL</span> or{' '}
              <span className="font-mono text-primary">NFP</span>.
            </div>
          )}

          {!showRecents && resolved && resolved.items.length === 0 && !store.universeLoading && (
            <div className="px-4 py-10 text-center">
              <div className="text-sm text-foreground font-medium mb-1">No results for “{store.query}”</div>
              <p className="text-xs text-muted-foreground/70">
                Try <span className="font-mono text-primary">AAPL</span>,{' '}
                <span className="font-mono text-primary">NFP</span>, or{' '}
                <span className="font-mono text-primary">portfolio</span>.
              </p>
            </div>
          )}

          {sections.map((section) => (
            <div key={section.key} className="mb-1.5">
              <div className="flex items-center justify-between px-4 pt-2 pb-1.5">
                <span className="text-[11px] font-medium text-muted-foreground/60">{section.label}</span>
                {section.key === 'recent' && (
                  <button
                    onClick={() => store.clearRecents()}
                    className="text-[10px] font-medium text-muted-foreground/50 hover:text-foreground transition-colors cursor-pointer"
                  >
                    Clear all
                  </button>
                )}
              </div>
              <div className="px-2 flex flex-col gap-px">
                {section.rows.map(({ row, flatIndex }) => (
                  <RowButton key={row.id} row={row} flatIndex={flatIndex} selected={flatIndex === store.selectedIndex} query={store.query} />
                ))}
              </div>
            </div>
          ))}

          {/* Pinned quick actions — dashed divider like Linear */}
          <div className="mx-4 my-2 border-t border-dashed border-border/60" />
          <div className="px-2 flex flex-col gap-px">
            {quickActions.map((qa) => {
              const flatIndex = flatRows.findIndex((r) => r.type === 'action' && r.id === qa.id);
              const row: Row = { type: 'action', id: qa.id, label: qa.label, icon: qa.icon, onSelect: qa.run };
              return <RowButton key={qa.id} row={row} flatIndex={flatIndex} selected={flatIndex === store.selectedIndex} query={store.query} />;
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="h-px bg-border/60" />
        <div className="px-4 py-2 flex items-center justify-between text-[10px] text-muted-foreground/50">
          <span className="flex items-center gap-1.5">
            <CornerDownLeft size={11} /> to select
            <span className="mx-1 text-muted-foreground/30">·</span>
            ↑↓ to navigate
            <span className="mx-1 text-muted-foreground/30">·</span>
            esc to close
          </span>
          {store.universeReady && <span>{indexCount.toLocaleString()} instruments indexed</span>}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Row renderer ─────────────────────────────────────────────────────────────

function RowButton({
  row,
  flatIndex,
  selected,
  query,
}: {
  row: Row;
  flatIndex: number;
  selected: boolean;
  query: string;
}) {
  const Icon =
    row.type === 'action' ? row.icon : row.type === 'recent' ? Search : KIND_ICON[row.kind] ?? Search;
  const label = row.type === 'action' ? row.label : row.type === 'recent' ? row.text : row.title;
  const subtitle = row.type === 'result' ? row.subtitle : null;

  return (
    <button
      onClick={row.onSelect}
      onMouseEnter={() => useCommandStore.getState().setSelectedIndex(flatIndex)}
      data-selected={selected || undefined}
      className={cn(
        'group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors',
        selected ? 'bg-accent text-foreground' : 'hover:bg-accent/30'
      )}
    >
      <span
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors',
          selected
            ? 'border-primary/30 bg-primary/15 text-primary'
            : 'border-border/60 bg-accent/40 text-muted-foreground/70'
        )}
      >
        <Icon size={15} />
      </span>
      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-sm', selected ? 'font-medium text-foreground' : 'text-foreground/90')}>
          <Highlight text={label} query={query} />
        </div>
        {subtitle && (
          <div className="mt-0.5 truncate text-[11px] text-muted-foreground/60">{subtitle}</div>
        )}
      </div>
      {row.type === 'recent' && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            row.onDelete();
          }}
          className="shrink-0 rounded p-1 text-muted-foreground/40 opacity-0 group-hover:opacity-100 hover:text-rose-400 transition-opacity cursor-pointer"
          title="Remove from recents"
        >
          <X size={13} />
        </button>
      )}
      {selected && row.type !== 'recent' && <CornerDownLeft size={13} className="shrink-0 text-muted-foreground/50" />}
    </button>
  );
}
