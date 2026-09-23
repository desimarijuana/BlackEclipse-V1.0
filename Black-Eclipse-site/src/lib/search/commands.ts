// ── Parameterized command detection ─────────────────────────────────────────
// Recognizes command signatures that take an argument and returns a suggestion
// list of candidate values (entities/params) so the palette can show inline
// autocomplete. The actual navigation is still produced by the registry action;
// this module only supplies the *parameter candidates* and a human label.
//
// Example: "alert AAPL" → the "alert" command with candidate instrument AAPL,
// so the palette can render "Set alert for AAPL" and preview the resolved arg.

import { getUniverseBySymbol, searchUniverse, universeRowToEntity } from './universe';
import { getAllInstruments, getInstrumentByAlias } from './registry';
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
// The only executable commands the palette renders are parameterized ones built
// by `paramCommandFor` below (e.g. "alert AAPL"). Each states what will happen,
// the target symbol, the bound shortcut, and a non-destructive side effect that
// runs BEFORE navigation: creating an alert or a watchlist entry.
//
// `paramCommandFor` and `commandShortcut` take their data as arguments so they
// are unit-testable and free of store reads.

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
