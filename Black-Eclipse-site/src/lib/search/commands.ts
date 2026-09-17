// ── Parameterized command detection ─────────────────────────────────────────
// Recognizes command signatures that take an argument and returns a suggestion
// list of candidate values (entities/params) so the palette can show inline
// autocomplete. The actual navigation is still produced by the registry action;
// this module only supplies the *parameter candidates* and a human label.
//
// Example: "alert AAPL" → the "alert" command with candidate instrument AAPL,
// so the palette can render "Set alert for AAPL" and preview the resolved arg.

import { getUniverseBySymbol, searchUniverse, universeRowToEntity } from './universe';
import {
  getAction,
  getAllInstruments,
  getInstrumentByAlias,
  getPage,
  getPageEntries,
} from './registry';
import { createQuickAlert } from '@/lib/alerts/quick-alert';
import { addToWatchlist } from '@/lib/dashboard/watchlist-store';
import type { SidebarConfig } from '@/lib/sidebar/config';
import type { AppTab, Destination, SearchEntity } from './types';

export interface ParamCandidate {
  value: string;
  label: string;
  subtitle: string;
}

export interface ParamCommand {
  /** The matched verb, e.g. 'alert'. */
  verb: ParamVerb;
  /** Remaining argument text (may be empty). */
  arg: string;
  /** Human template with a {arg} placeholder. */
  template: string;
}

// Verbs that take an instrument symbol argument, in the palette's vocabulary.
// Each verb has a real side effect wired in the palette (see global-search.tsx):
//   alert/alerts → create a ±3% CHANGE_PCT watch
//   watch        → add the symbol to the guest watchlist
//   chart        → open the symbol's chart
export type ParamVerb = 'alert' | 'alerts' | 'watch' | 'chart';

const PARAM_COMMANDS: { verb: ParamVerb; template: string }[] = [
  { verb: 'alert', template: 'Set price alert for {arg} (±3%)' },
  { verb: 'alerts', template: 'Set price alert for {arg} (±3%)' },
  { verb: 'watch', template: 'Add {arg} to watchlist' },
  { verb: 'chart', template: 'Chart {arg}' },
];

/** Detect a parameterized command at the start of the query. */
export function detectParamCommand(raw: string): ParamCommand | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const m = trimmed.match(/^([a-z]+)(?:\s+(.*))?$/i);
  if (!m) return null;
  const verb = m[1].toLowerCase();
  const cmd = PARAM_COMMANDS.find((c) => c.verb === verb);
  if (!cmd) return null;
  return { verb: cmd.verb, arg: (m[2] ?? '').trim(), template: cmd.template };
}

/** Candidate instrument args for the current argument fragment. */
export function paramCandidates(arg: string, limit = 5): ParamCandidate[] {
  const q = arg.trim();
  if (!q) return [];

  const out: ParamCandidate[] = [];
  const seen = new Set<string>();

  const push = (e: SearchEntity) => {
    const key = (e.symbol || e.title).toUpperCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ value: e.symbol || e.title, label: e.symbol || e.title, subtitle: e.title });
  };

  const exact = getUniverseBySymbol(q);
  if (exact) push(universeRowToEntity(exact));

  for (const e of getAllInstruments()) {
    if (out.length >= limit) break;
    if (e.symbol?.toLowerCase().startsWith(q.toLowerCase()) || e.title.toLowerCase().includes(q.toLowerCase())) {
      push(e);
    }
  }

  if (out.length < limit) {
    for (const row of searchUniverse(q, limit)) {
      if (out.length >= limit) break;
      push(universeRowToEntity(row));
    }
  }

  return out.slice(0, limit);
}

// ── Executable commands ──────────────────────────────────────────────────────
// The palette renders these as real rows: a human title stating what will
// happen, the target (symbol / fund name), the bound shortcut, and an optional
// side effect that runs BEFORE navigation. Everything here is non-destructive:
// creating an alert or a watchlist entry, or downloading a JSON export.
//
// Pure builders (`fundCommands`, `settingsCommands`, `paramCommandFor`,
// `rankCommands`, `commandShortcut`) take their data as arguments so they are
// unit-testable; `buildPaletteCommands` is the only store-reading assembler.

export interface ExecutableCommand {
  id: string;
  /** What the command will do, in plain language. */
  title: string;
  /** The thing it acts on (a symbol or fund name), when it has one. */
  target?: string;
  subtitle: string;
  icon?: string;
  /** Bound keyboard shortcut of the command's destination tab, if any. */
  shortcut?: string;
  keywords: string[];
  /** Where selecting navigates. `null` for a pure side-effect command. */
  destination: Destination | null;
  /** Side effect run before navigation. Never destructive. */
  run?: () => void | Promise<void>;
}

/** Bound shortcut (e.g. 'F7') for a tab, from the user's sidebar config. */
export function commandShortcut(tab: AppTab, cfg: SidebarConfig): string | undefined {
  const hit = cfg.sections.find((s) => s.id === tab && s.enabled && s.shortcut);
  return hit?.shortcut || undefined;
}

/** Resolve the symbol an `alert`/`watch`/`chart` argument refers to. */
export function resolveCommandSymbol(arg: string): string | null {
  const q = arg.trim();
  if (!q) return null;
  const candidate = paramCandidates(q, 1)[0];
  if (candidate?.value) return candidate.value.toUpperCase();
  const alias = getInstrumentByAlias(q);
  if (alias?.symbol) return alias.symbol.toUpperCase();
  const raw = q.toUpperCase().replace(/\s+/g, '');
  return /^[A-Z][A-Z0-9.=]{0,7}$/.test(raw) ? raw : null;
}

/**
 * Turn a detected parameterized command into an executable one. Returns null
 * when the verb has no wired side effect or the argument has no usable symbol.
 */
export function paramCommandFor(
  cmd: ParamCommand,
  cfg: SidebarConfig,
): ExecutableCommand | null {
  const symbol = resolveCommandSymbol(cmd.arg);
  if (!symbol) return null;

  if (cmd.verb === 'chart') {
    return {
      id: `cmd-chart-${symbol}`,
      title: `Chart ${symbol}`,
      target: symbol,
      subtitle: `Open the ${symbol} chart`,
      icon: 'candlestick',
      keywords: ['chart', 'open chart', symbol.toLowerCase()],
      destination: { tab: 'chart', params: { symbol } },
    };
  }

  if (cmd.verb === 'watch') {
    return {
      id: `cmd-watch-${symbol}`,
      title: `Add ${symbol} to watchlist`,
      target: symbol,
      subtitle: `Add ${symbol} to your watchlist · Command Center`,
      icon: 'pie',
      shortcut: commandShortcut('dashboard', cfg),
      keywords: ['watch', 'watchlist', 'add to watchlist', 'follow', symbol.toLowerCase()],
      destination: { tab: 'dashboard' },
      run: () => {
        addToWatchlist(symbol);
      },
    };
  }

  return {
    id: `cmd-alert-${symbol}`,
    title: `Set price alert for ${symbol} (±3%)`,
    target: symbol,
    subtitle: `Create a ±3% move alert for ${symbol} · Price Alerts`,
    icon: 'bell',
    shortcut: commandShortcut('alerts', cfg),
    keywords: ['alert', 'price alert', 'set alert', 'notify', symbol.toLowerCase()],
    destination: { tab: 'alerts' },
    run: async () => {
      await createQuickAlert(symbol, 3);
    },
  };
}

/** A fund the palette can open/export, from the search `user` entities. */
export interface FundRef {
  id: string;
  name: string;
}

/** Open-a-fund commands. The destination reuses the existing fund param. */
export function fundOpenCommands(funds: FundRef[], cfg: SidebarConfig): ExecutableCommand[] {
  return funds.map((fund) => ({
    id: `cmd-open-fund-${fund.id}`,
    title: `Open fund “${fund.name}”`,
    target: fund.name,
    subtitle: `Open ${fund.name} in Portfolio`,
    icon: 'briefcase',
    shortcut: commandShortcut('portfolio', cfg),
    keywords: ['open fund', 'fund', 'portfolio', fund.name.toLowerCase()],
    destination: { tab: 'portfolio', params: { fund: fund.id } },
  }));
}

/**
 * Export-a-fund commands. `exportFund` is the caller's real exporter (e.g.
 * `exportFundJson`); it is passed in so this module stays free of the fund
 * store and fully unit-testable.
 */
export function fundExportCommands(
  funds: FundRef[],
  exportFund: (fundId: string) => void,
  cfg: SidebarConfig,
): ExecutableCommand[] {
  return funds.map((fund) => ({
    id: `cmd-export-fund-${fund.id}`,
    title: `Export fund “${fund.name}”`,
    target: fund.name,
    subtitle: `Download ${fund.name} as JSON`,
    icon: 'briefcase',
    keywords: ['export fund', 'download fund', 'json', fund.name.toLowerCase()],
    destination: null,
    run: () => exportFund(fund.id),
  }));
}

/** Download-the-whole-book command (only when there is something to export). */
export function exportAllFundsCommand(
  funds: FundRef[],
  exportAll: () => void,
): ExecutableCommand | null {
  if (funds.length === 0) return null;
  const n = funds.length;
  return {
    id: 'cmd-export-all-funds',
    title: 'Export all portfolios',
    target: `${n} fund${n === 1 ? '' : 's'}`,
    subtitle: `Download ${n} fund${n === 1 ? '' : 's'} as JSON`,
    icon: 'briefcase',
    keywords: ['export', 'export portfolio', 'export all', 'download', 'json'],
    destination: null,
    run: () => exportAll(),
  };
}

/** One command per Settings section (the shell opens the modal at that section). */
export function settingsCommands(
  entries: Array<SearchEntity & { group: string; child: boolean }>,
  cfg: SidebarConfig,
): ExecutableCommand[] {
  return entries
    .filter((e) => e.destination.tab === 'settings' && e.destination.subroute)
    .map((e) => ({
      id: `cmd-${e.id}`,
      title: `Open Settings · ${e.title}`,
      subtitle: `Settings › ${e.title}`,
      icon: 'settings',
      shortcut: commandShortcut('settings', cfg),
      keywords: ['settings', e.title.toLowerCase(), e.destination.subroute!],
      destination: e.destination,
    }));
}

/** Match commands for a typed query (title, keywords, or target). */
export function rankCommands(
  commands: ExecutableCommand[],
  query: string,
  limit = 7,
): ExecutableCommand[] {
  const q = query.trim().toLowerCase();
  if (!q) return commands.slice(0, limit);
  const scored: Array<{ c: ExecutableCommand; score: number }> = [];
  for (const c of commands) {
    const title = c.title.toLowerCase();
    const target = c.target?.toLowerCase() ?? '';
    let score = 0;
    if (title.startsWith(q)) score = 100;
    else if (title.includes(q)) score = 80;
    else if (c.keywords.some((k) => k.toLowerCase().includes(q))) score = 60;
    else if (target && target.includes(q)) score = 40;
    if (score > 0) scored.push({ c, score });
  }
  scored.sort((a, b) => b.score - a.score || a.c.title.localeCompare(b.c.title));
  return scored.slice(0, limit).map((s) => s.c);
}

/**
 * Every static executable command the palette offers: journal, today's
 * economic events, and every Settings section. Reuses the registry's
 * page/action destinations (the action `run` is invoked for its real
 * destination, not for a side effect). Fund commands are added separately by
 * the palette, since they read the live fund book.
 */
export function buildPaletteCommands(cfg: SidebarConfig): ExecutableCommand[] {
  const out: ExecutableCommand[] = [];

  const journalAction = getAction('act-open-journal');
  const journalDest = journalAction?.run({ query: '', normalized: '' });
  if (journalDest) {
    out.push({
      id: 'cmd-open-journal',
      title: 'Open Trading Journal',
      subtitle: 'Journal tab',
      icon: 'book',
      shortcut: commandShortcut('journal', cfg),
      keywords: ['open journal', 'open trading journal', 'journal'],
      destination: journalDest,
    });
  }

  const journalCalendar = getPage('sub-journal-calendar');
  if (journalCalendar) {
    out.push({
      id: 'cmd-open-journal-calendar',
      title: 'Open Journal Calendar',
      subtitle: 'Journal › Calendar',
      icon: 'book',
      shortcut: commandShortcut('journal', cfg),
      keywords: ['journal calendar', 'journal', 'calendar'],
      destination: journalCalendar.destination,
    });
  }

  const econAction = getAction('act-open-econ-calendar');
  const econDest = econAction?.run({ query: '', normalized: '' });
  if (econDest) {
    out.push({
      id: 'cmd-econ-today',
      title: "Show today's economic events",
      subtitle: 'Economics › Calendar',
      icon: 'globe',
      shortcut: commandShortcut('economics', cfg),
      keywords: ['economic events today', 'today events', 'economic calendar', 'events', 'calendar'],
      destination: econDest,
    });
  }

  out.push(...settingsCommands(getPageEntries(), cfg));
  return out;
}
