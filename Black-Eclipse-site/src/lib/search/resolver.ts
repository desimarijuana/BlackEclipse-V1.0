// ── Resolver ────────────────────────────────────────────────────────────────
// Efficiently merges the small static registry (pages/indicators/actions) with
// the large universe index (55k+ assets). The universe is queried via O(1)
// exact-symbol lookup + FlexSearch — never by iterating all rows per keystroke.
//
// Priority: registry/indicator exact → universe exact symbol → static fuzzy →
// universe fuzzy. Returns a unified list of SearchItems.

import { getAllActions, getAllInstruments, getAllPages, getInstrumentByAlias } from './registry';
import { classifyIntent, extractSymbol } from './intent';
import { fuzzyScore, scoreEntity, suggestCorrection } from './rank';
import { getUserEntities } from './user';
import { getGlobalEntities } from './global';
import { settingsEntities } from './settings';
import { marketEntities } from './markets';
import { resolveEvent } from './events';
import { matchesFilters, parseQuery, scopeKinds, type ParsedQuery, type Scope } from './grammar';
import {
  getUniverseBySymbol,
  isUniverseLoaded,
  searchUniverse,
  universeRowToEntity,
} from './universe';
import type { Intent, SearchAction, SearchEntity } from './types';

export type { SearchEntity, SearchAction };

export interface SearchItem {
  entity: SearchEntity;
  score: number;
  match: 'exact' | 'prefix' | 'fuzzy' | 'keyword';
}

export interface ResolvedSearch {
  intent: Intent;
  items: SearchItem[];
  actions: SearchAction[];
  /** When intent is 'action', the top action to run on Enter. */
  primaryAction?: SearchAction;
  symbol?: string;
  /** True when the universe index finished loading (so we can show more). */
  universeReady: boolean;
  /** Total matches before the `maxResults` slice (drives "showing N of M"). */
  total: number;
  /** Best fuzzy correction offered when a query returns nothing. */
  suggestion?: string;
  /** Cross-entity shortcuts derived from the top instrument hit. */
  related: SearchEntity[];
  /** Scope + field filters parsed from the query grammar. */
  parsed: ParsedQuery;
  /** True when the query is a bare '?' asking for syntax help. */
  showHelp: boolean;
}

export interface ResolveOptions {
  currentTab?: string;
  recencyScore?: (id: string) => number;
  maxResults?: number;
}

// ── Deterministic query expansion ───────────────────────────────────────────
// A small, curated synonym/acronym table so natural phrasings and shorthand
// resolve without an LLM. Expansion produces *additional* normalized terms the
// registry scorer can match; it never replaces the user's own query.
const EXPANSIONS: { trigger: RegExp; terms: string[] }[] = [
  { trigger: /\bgold\b/, terms: ['xauusd', 'xau'] },
  { trigger: /\bsilver\b/, terms: ['xagusd', 'xag'] },
  { trigger: /\b(oil|crude|wti)\b/, terms: ['cl'] },
  { trigger: /\b(nasdaq|tech index)\b/, terms: ['ndx'] },
  { trigger: /\b(s&p|sp500|s&p 500)\b/, terms: ['spx'] },
  { trigger: /\b(dow|dow jones)\b/, terms: ['dji'] },
  { trigger: /\b(us jobs|jobs report|jobs data|payrolls|nonfarm|non-farm)\b/, terms: ['nfp'] },
  { trigger: /\b(inflation|consumer prices)\b/, terms: ['cpi'] },
  { trigger: /\b(fed rate|federal reserve|rate decision|interest rate decision)\b/, terms: ['fomc'] },
  { trigger: /\b(economic growth|domestic product)\b/, terms: ['gdp'] },
  { trigger: /\b(jobless|unemployment)\b/, terms: ['unemp'] },
  { trigger: /\b(british pound|pound sterling)\b/, terms: ['gbpusd'] },
  { trigger: /\b(yen|japanese yen)\b/, terms: ['usdjpy'] },
  { trigger: /\b(bitcoin)\b/, terms: ['btc'] },
  { trigger: /\b(ethereum|ether)\b/, terms: ['eth'] },
];

/** Expand a normalized query into extra search terms (does not include input). */
export function expandTerms(normalized: string): string[] {
  const out: string[] = [];
  for (const { trigger, terms } of EXPANSIONS) {
    if (trigger.test(normalized)) out.push(...terms);
  }
  return [...new Set(out)];
}

const KIND_BOOST: Record<string, number> = {
  indicator: 1.15,
  action: 1.1,
  security: 1.05,
  page: 1.0,
  instrument: 1.05,
};

function norm(s: string): string {
  return s.toLowerCase().replace(/\s+/g, ' ').trim();
}

function boostedScore(match: number, e: SearchEntity, currentTab?: string, recency = 0): number {
  let s = match * (KIND_BOOST[e.kind] ?? 1);
  if (e.rankBoost) s *= e.rankBoost;
  if (currentTab && e.destination.tab === currentTab) s *= 1.1;
  s *= 1 + recency * 0.15;
  return s;
}

export function resolveQuery(query: string, opts: ResolveOptions = {}): ResolvedSearch {
  const parsed = parseQuery(query);
  const scope: Scope = parsed.scope;
  const restrictedKinds = scopeKinds(scope);
  const text = parsed.text;

  const q = text.trim();
  const intent = classifyIntent(text);
  const normalized = norm(text);
  const recency = opts.recencyScore ?? (() => 0);
  const max = opts.maxResults ?? 12;

  // A bare scope prefix (">", "#", …) or a pure-help query has no terms to
  // resolve — the palette renders scope hints / the help card instead.
  if (!q) {
    return {
      intent: intent.intent,
      items: [],
      actions: [],
      universeReady: isUniverseLoaded(),
      total: 0,
      related: [],
      parsed,
      showHelp: parsed.showHelp,
    };
  }

  const items: SearchItem[] = [];

  const allowed = (e: SearchEntity): boolean => {
    if (restrictedKinds && !restrictedKinds.includes(e.kind)) return false;
    return matchesFilters(e, parsed.filters);
  };

  // ── 1. Registry exact (indicators, curated instruments, aliases) ─────────
  const regExact = getInstrumentByAlias(q);
  if (regExact && allowed(regExact)) {
    items.push({ entity: regExact, score: 1001, match: 'exact' });
  }

  // ── 2. Universe exact symbol (O(1)) ──────────────────────────────────────
  const uniExact = getUniverseBySymbol(q);
  if (uniExact) {
    const e = universeRowToEntity(uniExact);
    if (allowed(e)) items.push({ entity: e, score: 1000, match: 'exact' });
  }

  // ── 2b. Economic event (live calendar) — "next NFP", "CPI this month" ─────
  if (intent.intent === 'event' || intent.intent === 'indicator') {
    const ev = resolveEvent(q);
    if (ev && allowed(ev)) items.push({ entity: ev, score: 990, match: 'exact' });
  }

  // ── 3. Static registry fuzzy/prefix (small set — cheap to score) ─────────
  const staticEntities = [
    ...getAllPages(),
    ...getAllInstruments(),
    ...getUserEntities(),
    ...getGlobalEntities(),
    ...settingsEntities(),
    ...marketEntities(),
  ];
  for (const e of staticEntities) {
    if (!allowed(e)) continue;
    if (regExact && e.id === regExact.id) continue;
    const s = scoreEntity({ entity: e, query: normalized, currentTab: opts.currentTab, recencyScore: recency(e.id) });
    if (s > 0) {
      items.push({ entity: e, score: boostedScore(s, e, opts.currentTab, recency(e.id)), match: matchKind(s) });
      continue;
    }
    // Synonym/acronym expansion — score against derived terms at a discount so
    // an explicit word match always outranks an inferred one.
    let expanded = false;
    for (const term of expandTerms(normalized)) {
      const es = scoreEntity({ entity: e, query: term, currentTab: opts.currentTab, recencyScore: recency(e.id) });
      if (es > 0) {
        items.push({ entity: e, score: boostedScore(es * 0.85, e, opts.currentTab, recency(e.id)), match: 'keyword' });
        expanded = true;
        break;
      }
    }
    if (expanded) continue;
    // Fuzzy fallback on the small static set (cheap, handles "Aplle").
    const f = fuzzyScore(e, normalized, 2);
    if (f > 0) items.push({ entity: e, score: f, match: 'fuzzy' });
  }

  // ── 4. Universe fuzzy (FlexSearch — fast) ────────────────────────────────
  // Only when the query is a plausible instrument query and the scope allows
  // securities, to avoid polluting page/action lookups with thousands of rows.
  const isInstrumentQuery =
    intent.intent === 'entity' ||
    intent.intent === 'indicator' ||
    intent.intent === 'data' ||
    intent.intent === 'unknown' ||
    scope === 'symbol';
  const symbolScope = !restrictedKinds || restrictedKinds.includes('security') || restrictedKinds.includes('instrument');
  if (isInstrumentQuery && symbolScope && q.length >= 2) {
    const hits = searchUniverse(q, 6);
    for (const row of hits) {
      const sym = row.symbol.toLowerCase();
      if (sym === normalized || (regExact && regExact.symbol?.toLowerCase() === sym)) continue;
      const e = universeRowToEntity(row);
      if (!allowed(e)) continue;
      // Prefix/symbol matches rank above fuzzy name matches.
      const isSymPrefix = row.symbol.toLowerCase().startsWith(normalized);
      const score = isSymPrefix ? 700 : 520;
      items.push({ entity: e, score: boostedScore(score, e, opts.currentTab), match: isSymPrefix ? 'prefix' : 'fuzzy' });
    }
  }

  // ── 5. Actions (command palette) ─────────────────────────────────────────
  const actionScope = !restrictedKinds || restrictedKinds.includes('action');
  const actions = actionScope
    ? getAllActions().filter((a) => {
        if (a.static && normalized.length < 2) return false;
        return (
          normalized.includes(a.title.toLowerCase()) ||
          a.keywords.some((k) => normalized.includes(k)) ||
          a.title.toLowerCase().includes(normalized)
        );
      })
    : [];

  let primaryAction: SearchAction | undefined;
  if ((intent.intent === 'action' || scope === 'action') && actions.length > 0) {
    primaryAction = actions[0];
    const actionCtx = { query: text, normalized, symbol: extractSymbol(text) };
    const actionItems: SearchItem[] = actions.map((a, i) => {
      // Execute the action's own `run()` so selecting a command navigates to
      // its real destination (e.g. "Open Portfolio" → portfolio tab) instead
      // of always falling through to the chat tab.
      let destination: SearchEntity['destination'] = { tab: 'chat' };
      try {
        const d = a.run(actionCtx);
        if (d) destination = d;
      } catch {
        /* keep the chat fallback if a run handler throws */
      }
      return {
        entity: {
          id: a.id,
          kind: 'action',
          title: a.title,
          keywords: a.keywords,
          icon: a.icon,
          destination,
        },
        score: 2000 - i,
        match: 'keyword',
      };
    });
    items.push(...actionItems);
  }

  // Sort: score desc, then title asc for stability.
  items.sort((a, b) => b.score - a.score || a.entity.title.localeCompare(b.entity.title));

  // Dedupe: the same instrument can arrive from both the curated registry and
  // the universe index (e.g. AAPL). Keep the highest-scored row per symbol so
  // users never see the identical asset listed twice.
  const seen = new Set<string>();
  const deduped = items.filter((it) => {
    const e = it.entity;
    const key = e.symbol ? `sym:${e.symbol.toUpperCase()}` : `id:${e.id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const sliced = deduped.slice(0, max);
  const result: ResolvedSearch = {
    intent: primaryAction ? 'action' : intent.intent,
    items: sliced,
    actions,
    primaryAction,
    symbol: extractSymbol(text),
    universeReady: !!getUniverseBySymbol(q) || isUniverseBuilt(),
    total: deduped.length,
    related: [],
    parsed,
    showHelp: parsed.showHelp,
  };

  // Cross-entity shortcuts: when the query lands on a specific instrument,
  // offer quick pivots into other tabs for that same symbol.
  if (!restrictedKinds && !primaryAction) {
    const top = sliced.find((it) => it.entity.symbol && (it.entity.kind === 'security' || it.entity.kind === 'instrument'));
    if (top?.entity.symbol) {
      result.related = relatedEntities(top.entity);
    }
  }

  // No hits at all → offer the nearest registry title as "did you mean …".
  // Uses only the small static set, so it is cheap and never runs on the
  // universe fuzzy path.
  if (sliced.length === 0 && !primaryAction) {
    result.suggestion = suggestCorrection(text, staticEntities);
  }

  return result;
}

/** Tab pivots offered alongside a resolved instrument (e.g. "AAPL news"). */
function relatedEntities(entity: SearchEntity): SearchEntity[] {
  const symbol = entity.symbol!;
  const mk = (suffix: string, tab: SearchEntity['destination']['tab'], params: Record<string, string>): SearchEntity => ({
    id: `rel-${symbol}-${suffix}`,
    kind: 'page',
    title: `${symbol} ${suffix}`,
    keywords: [symbol, suffix],
    destination: { tab, params: { symbol, ...params } },
    subtitle: `Open ${suffix}`,
    rankBoost: 0.6,
  });
  return [
    mk('news', 'news', { symbol }),
    mk('chart', 'chart', { symbol }),
    mk('screener', 'discovery', { symbol }),
  ];
}

function matchKind(s: number): SearchItem['match'] {
  if (s >= 1000) return 'exact';
  if (s >= 600) return 'prefix';
  return 'keyword';
}

function isUniverseBuilt(): boolean {
  return isUniverseLoaded();
}
