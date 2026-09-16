// ── GlobalSearch — universal command center ────────────────────────────────
// Linear-style command menu in the Black Eclipse design language: grouped
// sections with icon tiles, inset highlighted rows, breadcrumb subtitles, and
// pinned quick actions at the bottom. Searches pages, indicators, actions, and
// the full JDDS universe (55k+ assets via FlexSearch). Fully offline.

'use client';

import { memo, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot,
  BookOpen,
  Briefcase,
  ChartCandlestick,
  ChartPie,
  ScanSearch,
  Globe,
  Search,
  CornerDownLeft,
  Plus,
  Loader2,
  X,
  Pin,
  ChevronRight,
  Copy,
  Check,
  Calculator,
  Bell,
  LayoutDashboard,
  Newspaper,
  Orbit,
  Settings,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { useCommandStore, visitRecencyScore } from '@/lib/search/store';
import { resolveQuery } from '@/lib/search/resolver';
import { evaluateCalc, type CalcResult } from '@/lib/search/calc';
import { detectParamCommand, paramCandidates } from '@/lib/search/commands';
import { createQuickAlert } from '@/lib/alerts/quick-alert';
import { addToWatchlist } from '@/lib/dashboard/watchlist-store';
import { universeCount } from '@/lib/search/universe';
import { getPage } from '@/lib/search/registry';
import { DEFAULT_SCOPE, SCOPES, parseQuery, type ScopeMeta } from '@/lib/search/grammar';
import { useCommandCenterKeybind } from '@/hooks/use-command-center-keybind';
import type { EntityKind, SearchEntity } from '@/lib/search/types';

/**
 * Map the registry's string icon names (used by pages/instruments/actions) to
 * lucide components. Kept local to the palette because it is the only consumer
 * that renders those strings. Unknown names fall back to a generic glyph.
 */
const NAME_ICON: Record<string, LucideIcon> = {
  dashboard: LayoutDashboard,
  chart: ChartCandlestick,
  candlestick: ChartCandlestick,
  screen: ScanSearch,
  pie: ChartPie,
  bot: Bot,
  briefcase: Briefcase,
  book: BookOpen,
  news: Newspaper,
  orbit: Orbit,
  globe: Globe,
  bell: Bell,
  settings: Settings,
};

function nameIcon(name?: string): LucideIcon {
  return (name && NAME_ICON[name]) || Sparkles;
}

/**
 * Top-level pages shown in the palette's Pages list, in sidebar order
 * (ChatBot → … → Price Alerts). Deliberately excludes `settings` (a modal) and
 * the retired `chart` tab.
 */
const TOP_LEVEL_PAGE_IDS = [
  'page-chat',
  'page-dashboard',
  'page-investor-eye',
  'page-market-workspace',
  'page-screener',
  'page-portfolio',
  'page-journal',
  'page-news',
  'page-heatmap',
  'page-economics',
  'page-alerts',
];

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

/**
 * Section a row belongs to. `security` (JDDS assets) and `instrument` (curated
 * registry entries, e.g. indices) both render as "Instruments", so they MUST
 * share one section — otherwise the grouping splits them and the second section
 * re-sorts by nothing, burying a high-scoring index under low-scoring ETFs that
 * merely matched the same words. Rows keep the resolver's score order inside.
 */
function sectionKeyOf(kind: EntityKind): string {
  return kind === 'security' || kind === 'instrument' ? 'instruments' : kind;
}

const SECTION_ORDER: string[] = [
  'action',
  'page',
  'indicator',
  'event',
  'instruments',
  'report',
  'agent',
  'doc',
  'user',
];

const SECTION_LABEL: Record<string, string> = {
  action: 'Commands',
  page: 'Navigation',
  indicator: 'Economic Indicators',
  event: 'Economic Indicators',
  instruments: 'Instruments',
  report: 'Reports',
  agent: 'Agents',
  doc: 'Docs',
  user: 'Your data',
};

/** Rows moved per PageUp/PageDown in the results list. */
const PAGE_SIZE = 6;

interface QuickAction {
  id: string;
  label: string;
  icon: LucideIcon;
  run: () => void;
}

type Row =
  | { type: 'recent'; id: string; text: string; onSelect: () => void; onDelete: () => void }
  | { type: 'result'; id: string; title: string; subtitle: string; kind: EntityKind; entity: SearchEntity; onSelect: () => void; pinned?: boolean }
  | { type: 'action'; id: string; label: string; icon: LucideIcon; onSelect: () => void };

interface Section {
  key: string;
  label: string;
  /** Total rows in the group before any cap (drives the count badge). */
  count: number;
  /** True when the user collapsed this group (rows render but are skipped). */
  collapsed: boolean;
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
  // Whether the results list can still scroll down (drives the bottom fade).
  const [canScrollDown, setCanScrollDown] = useState(false);

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
  // calendar, or server-side entities finish loading. Recency personalizes the
  // ranking from the user's own visit history (kept off the resolver's hot path).
  const resolved = useMemo(() => {
    const q = debouncedQuery.trim();
    if (!q) return null;
    const visits = useCommandStore.getState().visits;
    return resolveQuery(q, { recencyScore: (id) => visitRecencyScore(visits, id) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, store.universeReady, store.calendarReady, store.globalReady, store.visits]);

  const showRecents = !debouncedQuery.trim();
  const indexCount = universeCount();
  const activeScope: ScopeMeta = useMemo(() => {
    const { scope } = parseQuery(store.query);
    return SCOPES.find((s) => s.scope === scope) ?? DEFAULT_SCOPE;
  }, [store.query]);
  const showHelp = !!(resolved && resolved.showHelp);
  // A bare scope prefix (e.g. ">") — no terms yet, so nudge with scope hints
  // instead of the generic empty state.
  const bareScope = !showHelp && !showRecents && !!resolved && activeScope.scope !== 'all' && !resolved.parsed.text.trim();
  // Pages-group collapse (shares the store's collapsedGroups list).
  const navCollapsed = store.collapsedGroups.includes('nav');

  // The Pages list = the app's top-level tabs only, in sidebar order. Typing
  // still searches everything (instruments, indicators, markets, actions);
  // this list is purely the page launcher.
  const navPages: QuickAction[] = useMemo(
    () =>
      TOP_LEVEL_PAGE_IDS.map((id) => getPage(id))
        .filter((p): p is SearchEntity => Boolean(p))
        .map((p) => ({
          id: `nav-${p.id}`,
          label: p.title,
          icon: nameIcon(p.icon),
          run: () => {
            store.dispatch(p.destination);
            useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
          },
        })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Flat navigable list = the page launcher (order matches render).
  const quickActions: QuickAction[] = navPages;

  // Build sections + a flat navigable row list (collapsed groups are skipped).
  const { sections, flatRows, hasAiRow } = useMemo(() => {
    const flat: Row[] = [];
    interface DraftSection {
      key: string;
      label: string;
      count: number;
      collapsed: boolean;
      rows: Row[];
    }
    const built: DraftSection[] = [];

    // AI escalation row — shown for sentence-like questions. Built BEFORE any
    // section flatIndex is assigned so navigation indices stay in sync, and
    // rendered as its own section (it used to be unshifted but never shown).
    const aiRow: Row | null = (!showRecents && resolved && resolved.intent === 'ai' && debouncedQuery.trim())
      ? {
          type: 'action',
          id: 'ai-ask',
          label: `Ask AI: “${debouncedQuery}”`,
          icon: Bot,
          onSelect: () => {
            store.dispatch({ tab: 'chat', params: { prompt: debouncedQuery } });
            useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
          },
        }
      : null;

    if (showRecents) {
      if (store.pins.length > 0) {
        const rows = store.pins.map<Row>((p) => {
          const entity: SearchEntity = {
            id: p.id,
            kind: p.kind as EntityKind,
            title: p.title,
            symbol: p.symbol,
            keywords: [],
            destination: { tab: p.tab as SearchEntity['destination']['tab'], params: p.params },
            subtitle: p.subtitle,
          };
          return {
            type: 'result',
            id: `pin-${p.id}`,
            title: p.symbol ? `${p.symbol}  ${p.title}` : p.title,
            subtitle: p.subtitle || KIND_LABEL[p.kind as EntityKind] || 'Pinned',
            kind: p.kind as EntityKind,
            entity,
            pinned: true,
            onSelect: () => {
              store.recordVisit(p.id);
              store.dispatch(entity.destination);
              store.recordRecent(p.symbol || p.title);
              useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
            },
          };
        });
        built.push({ key: 'pinned', label: 'Pinned', count: rows.length, collapsed: false, rows });
      }
      if (store.recents.length > 0) {
        const rows = store.recents.map<Row>((r) => ({
          type: 'recent',
          id: 'recent-' + r.ts,
          text: r.text,
          onSelect: () => store.setQuery(r.text),
          onDelete: () => store.removeRecent(r.text),
        }));
        built.push({ key: 'recent', label: 'Recent searches', count: rows.length, collapsed: false, rows });
      }
    } else {
      if (aiRow) built.push({ key: 'ai', label: 'Ask AI', count: 1, collapsed: false, rows: [aiRow] });
      if (resolved && resolved.items.length > 0) {
        // Group by SECTION key (not raw kind) so `security` + `instrument` land
        // in one "Instruments" list that preserves the resolver's score order.
        const byKind = new Map<string, Row[]>();
        resolved.items.forEach((it) => {
          const kind = it.entity.kind;
          const key = sectionKeyOf(kind);
          const list = byKind.get(key) ?? [];
          const dest = it.entity.destination;
          list.push({
            type: 'result',
            id: it.entity.id,
            title: it.entity.symbol ? `${it.entity.symbol}  ${it.entity.title}` : it.entity.title,
            subtitle: it.entity.subtitle || KIND_LABEL[kind],
            kind,
            entity: it.entity,
            pinned: store.pins.some((p) => p.id === it.entity.id),
            onSelect: () => {
              if (dest) {
                store.recordVisit(it.entity.id);
                store.dispatch(dest);
                store.recordRecent(it.entity.symbol || store.query);
                useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
              }
            },
          });
          byKind.set(key, list);
        });
        for (const key of SECTION_ORDER.filter((k) => byKind.has(k))) {
          const rows = byKind.get(key)!;
          built.push({
            key,
            label: SECTION_LABEL[key],
            count: rows.length,
            collapsed: store.collapsedGroups.includes(key),
            rows,
          });
        }
      }
      // Cross-entity pivots for the top instrument hit (AAPL news / chart / …).
      if (resolved && resolved.related.length > 0) {
        const rows = resolved.related.map<Row>((e) => ({
          type: 'result',
          id: e.id,
          title: e.title,
          subtitle: e.subtitle || 'Related',
          kind: e.kind,
          entity: e,
          onSelect: () => {
            store.dispatch(e.destination);
            useCommandStore.setState({ open: false, query: '', resolved: null, selectedIndex: 0 });
          },
        }));
        built.push({ key: 'related', label: 'Related', count: rows.length, collapsed: store.collapsedGroups.includes('related'), rows });
      }
    }

    // Assign flat indices in render order, skipping collapsed groups. Collapsed
    // sections stay in the list (header only) so the toggle remains clickable.
    const sections: Section[] = built.map((s) => {
      const rows = s.collapsed
        ? []
        : s.rows.map((row) => {
            flat.push(row);
            return { row, flatIndex: flat.length - 1 };
          });
      return { key: s.key, label: s.label, count: s.count, collapsed: s.collapsed, rows };
    });

    // Pinned navigation commands at the bottom (part of the flat list).
    // Suppressed while the syntax help card is open, and skipped when the
    // Pages group is collapsed.
    if (!showHelp && !navCollapsed) {
      for (const qa of quickActions) {
        flat.push({ type: 'action', id: qa.id, label: qa.label, icon: qa.icon, onSelect: qa.run });
      }
    }

    return { sections, flatRows: flat, hasAiRow: !!aiRow };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, store.recents, store.pins, store.collapsedGroups, store.universeReady, resolved, showRecents, quickActions, showHelp, navCollapsed]);
  // Track whether more content exists below the fold so the fade can show/hide.
  // Re-measured when the flat list changes (query, collapse, pins, …).
  useEffect(() => {
    const container = resultsRef.current;
    if (!container) return;
    const measure = () => {
      setCanScrollDown(container.scrollTop + container.clientHeight < container.scrollHeight - 4);
    };
    measure();
    container.addEventListener('scroll', measure, { passive: true });
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(container);
    return () => {
      container.removeEventListener('scroll', measure);
      ro?.disconnect();
    };
  }, [store.open, flatRows.length]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const count = flatRows.length;
    if (count === 0) {
      if (e.key === 'Enter') {
        e.preventDefault();
        store.runPrimary();
      }
      return;
    }
    const last = count - 1;
    const clamp = (i: number) => Math.max(0, Math.min(last, i));
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      store.setSelectedIndex((store.selectedIndex + 1) % count);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      store.setSelectedIndex((store.selectedIndex - 1 + count) % count);
    } else if (e.key === 'PageDown') {
      // Jump a page in the list, keeping the active row visible.
      e.preventDefault();
      store.setSelectedIndex(clamp(store.selectedIndex + PAGE_SIZE));
    } else if (e.key === 'PageUp') {
      e.preventDefault();
      store.setSelectedIndex(clamp(store.selectedIndex - PAGE_SIZE));
    } else if (e.key === 'Home') {
      e.preventDefault();
      store.setSelectedIndex(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      store.setSelectedIndex(last);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const row = flatRows[clamp(store.selectedIndex)];
      if (row) row.onSelect();
      else {
        store.runPrimary();
      }
    }
  };

  return (
    <Dialog open={store.open} onOpenChange={(o) => store.setOpen(o)}>
      <DialogContent
        showCloseButton={false}
        className="command-glass top-0 translate-y-0 left-1/2 -translate-x-1/2 sm:max-w-lg max-w-[calc(100%-1rem)] mt-2 sm:mt-5 w-full p-0 gap-0 rounded-xl overflow-hidden"
      >
        <DialogTitle className="sr-only">Global Search</DialogTitle>

        {/* Input row */}
        <div className="flex items-center gap-3 px-4 py-3.5">
          <Search size={17} className="text-muted-foreground/70 shrink-0" />
          {activeScope.scope !== 'all' && (
            <span className="flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/15 px-2 py-1 text-[11px] font-medium text-primary shrink-0">
              <span className="font-mono">{activeScope.prefix}</span>
              {activeScope.label}
            </span>
          )}
          <input
            ref={inputRef}
            value={store.query}
            onChange={(e) => store.setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={activeScope.placeholder}
            className="h-8 flex-1 border-0 bg-transparent outline-none px-0 font-mono text-[15px] text-foreground placeholder:text-muted-foreground/60"
            autoComplete="off"
            spellCheck={false}
            role="combobox"
            aria-expanded={store.open}
            aria-controls="command-results"
            aria-autocomplete="list"
            aria-activedescendant={flatRows.length > 0 ? `command-opt-${Math.min(store.selectedIndex, flatRows.length - 1)}` : undefined}
            aria-label="Global search"
          />
          {store.universeLoading && <Loader2 size={14} className="animate-spin text-muted-foreground/60 shrink-0" />}
          {store.query && (
            <button
              onClick={() => store.setQuery('')}
              className="shrink-0 rounded p-1 text-muted-foreground/40 hover:text-foreground transition-colors cursor-pointer"
              title="Clear search"
            >
              <X size={13} />
            </button>
          )}
        </div>

        <div className="h-px bg-border/60" />

        {/* Results — wrapped so a bottom fade signals more below the fold. */}
        <div className="relative">
        <div ref={resultsRef} id="command-results" role="listbox" aria-label="Search results" className="max-h-[min(70dvh,400px)] sm:max-h-[min(50dvh,400px)] overflow-y-auto py-2">
          {showHelp && <SyntaxHelp onPick={(p) => store.setQuery(p)} />}

          {bareScope && (
            <div className="px-4 py-6 text-center text-xs text-muted-foreground/70">
              <span className="font-mono text-primary">{activeScope.prefix}</span> {activeScope.hint} — start typing, or type{' '}
              <span className="font-mono text-primary">?</span> for all syntax.
            </div>
          )}

          {showRecents && sections.length === 0 && (
            <div className="px-4 py-8 text-center text-xs text-muted-foreground/60">
              No recent searches yet — try a symbol like{' '}
              <span className="font-mono text-primary">AAPL</span> or{' '}
              <span className="font-mono text-primary">NFP</span>. Type{' '}
              <button
                onClick={() => store.setQuery('?')}
                className="font-mono text-primary hover:underline cursor-pointer"
              >
                ?
              </button>{' '}
              for syntax.
            </div>
          )}

          {!showRecents && !showHelp && !bareScope && resolved && resolved.items.length === 0 && !hasAiRow && !store.universeLoading && (
            <div className="px-4 py-10 text-center">
              <div className="text-sm text-foreground font-medium mb-1">No results for “{store.query}”</div>
              {resolved.suggestion ? (
                <p className="text-xs text-muted-foreground/70">
                  Did you mean{' '}
                  <button
                    onClick={() => store.setQuery(resolved.suggestion!)}
                    className="font-medium text-primary hover:underline cursor-pointer"
                  >
                    {resolved.suggestion}
                  </button>
                  ?
                </p>
              ) : (
                <p className="text-xs text-muted-foreground/70">
                  Try <span className="font-mono text-primary">AAPL</span>,{' '}
                  <span className="font-mono text-primary">NFP</span>, or{' '}
                  <span className="font-mono text-primary">portfolio</span>.
                </p>
              )}
            </div>
          )}

          {sections.map((section) => (
            <div key={section.key} className="mb-1.5">
              <div className="flex items-center justify-between px-4 pt-2 pb-1.5">
                <button
                  onClick={() => section.key !== 'recent' && section.key !== 'pinned' && store.toggleGroup(section.key)}
                  className={cn(
                    'flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground/60',
                    section.key !== 'recent' && section.key !== 'pinned' && 'hover:text-foreground transition-colors cursor-pointer',
                  )}
                >
                  {section.key !== 'recent' && section.key !== 'pinned' && (
                    <ChevronRight
                      size={11}
                      className={cn('transition-transform', !section.collapsed && 'rotate-90')}
                    />
                  )}
                  {section.label}
                  <span className="text-muted-foreground/40">{section.count}</span>
                </button>
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
                  <RowButton
                    key={row.id}
                    row={row}
                    flatIndex={flatIndex}
                    selected={flatIndex === store.selectedIndex}
                    query={store.query}
                    onTogglePin={store.togglePin}
                  />
                ))}
              </div>
            </div>
          ))}

          {/* Go-to navigation — every registered page, generated from the
              registry. Collapsible + part of the scrollable/keyboard list.
              Hidden while the syntax help card is open. */}
          {!showHelp && (
            <>
              <div className="mx-4 my-2 border-t border-dashed border-border/60" />
              <div className="flex items-center justify-between px-4 pt-2 pb-1.5">
                <button
                  onClick={() => store.toggleGroup('nav')}
                  className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground/60 hover:text-foreground transition-colors cursor-pointer"
                >
                  <ChevronRight size={11} className={cn('transition-transform', !navCollapsed && 'rotate-90')} />
                  Pages
                  <span className="text-muted-foreground/40">{navPages.length}</span>
                </button>
              </div>
              <div className="px-2 flex flex-col gap-px">
                {navCollapsed
                  ? null
                  : navPages.map((qa) => {
                      const flatIndex = flatRows.findIndex((r) => r.type === 'action' && r.id === qa.id);
                      const row: Row = { type: 'action', id: qa.id, label: qa.label, icon: qa.icon, onSelect: qa.run };
                      return <RowButton key={qa.id} row={row} flatIndex={flatIndex} selected={flatIndex === store.selectedIndex} query={store.query} onTogglePin={store.togglePin} />;
                    })}
              </div>
            </>
          )}
        </div>
          {/* Scroll affordance — pointer-events-none so rows stay clickable.
              Only shown when there is more content below the fold. */}
          {canScrollDown && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-black/35 dark:from-black/50 to-transparent" />
          )}
        </div>

        {/* Footer */}
        <div className="h-px bg-border/60" />
        <div className="px-4 py-2 flex items-center justify-between text-[10px] text-muted-foreground/50">
          <span className="flex items-center gap-1.5">
            <CornerDownLeft size={11} /> to select
            <span className="mx-1 text-muted-foreground/30">·</span>
            ↑↓ navigate
            <span className="mx-1 text-muted-foreground/30">·</span>
            <span title="PageUp / PageDown">PgUp/Dn</span>
            <span className="mx-1 text-muted-foreground/30">·</span>
            esc to close
            <span className="mx-1 text-muted-foreground/30">·</span>
            <button
              onClick={() => store.setQuery('?')}
              className="font-mono hover:text-foreground transition-colors cursor-pointer"
              title="Search syntax"
            >
              ?
            </button>{' '}
            for syntax
          </span>
          {store.universeReady && (
            <span>
              {resolved && resolved.total > resolved.items.length
                ? `${resolved.items.length} of ${resolved.total.toLocaleString()} results`
                : `${indexCount.toLocaleString()} instruments indexed`}
            </span>
          )}
        </div>

        {/* Screen-reader result announcement (visual footer stays terse). */}
        <div className="sr-only" role="status" aria-live="polite">
          {resolved && !showRecents
            ? `${resolved.items.length} result${resolved.items.length === 1 ? '' : 's'} for ${store.query}`
            : ''}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Syntax help ──────────────────────────────────────────────────────────────

function SyntaxHelp({ onPick }: { onPick: (q: string) => void }) {
  const operators: { token: string; desc: string }[] = [
    { token: 'kind:crypto', desc: 'filter by entity kind' },
    { token: 'class:etf', desc: 'filter by asset class' },
    { token: 'market:us', desc: 'filter by market' },
    { token: 'symbol:aapl', desc: 'match a symbol' },
  ];
  return (
    <div className="px-4 py-3">
      <div className="mb-2 text-[11px] font-medium text-muted-foreground/60">Search syntax</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
        {SCOPES.map((s) => (
          <button
            key={s.scope}
            onClick={() => onPick(`${s.prefix} `)}
            className="group flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-accent/30 transition-colors cursor-pointer"
          >
            <kbd className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-border/60 bg-accent/40 font-mono text-[11px] text-muted-foreground/70 group-hover:text-primary group-hover:border-primary/30">
              {s.prefix}
            </kbd>
            <span className="min-w-0 flex-1">
              <span className="block text-sm text-foreground/90">{s.hint}</span>
            </span>
          </button>
        ))}
      </div>
      <div className="mt-3 border-t border-dashed border-border/60 pt-3">
        <div className="mb-2 text-[11px] font-medium text-muted-foreground/60">Operators</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
          {operators.map((o) => (
            <button
              key={o.token}
              onClick={() => onPick(`${o.token} `)}
              className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-accent/30 transition-colors cursor-pointer"
            >
              <kbd className="shrink-0 rounded-md border border-border/60 bg-accent/40 px-2 py-0.5 font-mono text-[11px] text-muted-foreground/70">
                {o.token}
              </kbd>
              <span className="truncate text-xs text-muted-foreground/70">{o.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Row renderer ─────────────────────────────────────────────────────────────
// Memoized: hovering/arrowing changes only `selected`, and every row object is
// rebuilt only when the resolved sections change — so memo skips re-rendering
// the dozens of untouched rows on each selection change.

const RowButton = memo(function RowButton({
  row,
  flatIndex,
  selected,
  query,
  onTogglePin,
}: {
  row: Row;
  flatIndex: number;
  selected: boolean;
  query: string;
  onTogglePin: (pin: { id: string; title: string; symbol?: string; kind: string; tab: string; params?: Record<string, string>; subtitle?: string }) => void;
}) {
  const [copied, setCopied] = useState(false);
  const Icon =
    row.type === 'action' ? row.icon : row.type === 'recent' ? Search : KIND_ICON[row.kind] ?? Search;
  const label = row.type === 'action' ? row.label : row.type === 'recent' ? row.text : row.title;
  const subtitle = row.type === 'result' ? row.subtitle : null;
  const onSelect = row.onSelect;

  const copySymbol = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (row.type !== 'result' || !row.entity.symbol) return;
    void navigator.clipboard?.writeText(row.entity.symbol).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };

  const togglePin = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (row.type !== 'result') return;
    const e2 = row.entity;
    onTogglePin({
      id: e2.id,
      title: e2.title,
      symbol: e2.symbol,
      kind: e2.kind,
      tab: e2.destination.tab,
      params: e2.destination.params,
      subtitle: e2.subtitle,
    });
  };

  return (
    <div
      id={`command-opt-${flatIndex}`}
      role="option"
      aria-selected={selected}
      tabIndex={-1}
      onClick={onSelect}
      onMouseEnter={() => useCommandStore.getState().setSelectedIndex(flatIndex)}
      data-selected={selected || undefined}
      className={cn(
        'group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors cursor-pointer',
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

      {row.type === 'result' && (
        <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
          {row.entity.symbol && (
            <button
              onClick={copySymbol}
              className="rounded p-1 text-muted-foreground/40 hover:text-foreground transition-colors cursor-pointer"
              title="Copy symbol"
            >
              {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
            </button>
          )}
          <button
            onClick={togglePin}
            className={cn(
              'rounded p-1 transition-colors cursor-pointer',
              row.pinned ? 'text-primary' : 'text-muted-foreground/40 hover:text-foreground',
            )}
            title={row.pinned ? 'Unpin' : 'Pin'}
          >
            <Pin size={13} className={row.pinned ? 'fill-current' : ''} />
          </button>
        </div>
      )}

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
    </div>
  );
});
