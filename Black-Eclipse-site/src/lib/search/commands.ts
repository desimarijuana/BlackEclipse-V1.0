// ── Parameterized command detection ─────────────────────────────────────────
// Recognizes command signatures that take an argument and returns a suggestion
// list of candidate values (entities/params) so the palette can show inline
// autocomplete. The actual navigation is still produced by the registry action;
// this module only supplies the *parameter candidates* and a human label.
//
// Example: "alert AAPL" → the "alert" command with candidate instrument AAPL,
// so the palette can render "Set alert for AAPL" and preview the resolved arg.

import { getUniverseBySymbol, searchUniverse, universeRowToEntity } from './universe';
import { getAllInstruments } from './registry';
import type { SearchEntity } from './types';

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
