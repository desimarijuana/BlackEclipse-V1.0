// ── Resolver ────────────────────────────────────────────────────────────────
// Efficiently merges the small static registry (pages/indicators/actions) with
// the large universe index (55k+ assets). The universe is queried via O(1)
// exact-symbol lookup + FlexSearch — never by iterating all rows per keystroke.
//
// Priority: registry/indicator exact → universe exact symbol → static fuzzy →
// universe fuzzy. Returns a unified list of SearchItems.

import { getAllActions, getAllInstruments, getAllPages, getInstrumentByAlias } from './registry';
import { classifyIntent, extractSymbol } from './intent';
import { fuzzyScore, scoreEntity } from './rank';
import { getUserEntities } from './user';
import { getGlobalEntities } from './global';
import { settingsEntities } from './settings';
import { marketEntities } from './markets';
import { resolveEvent } from './events';
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
}

export interface ResolveOptions {
  currentTab?: string;
  recencyScore?: (id: string) => number;
  maxResults?: number;
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
  const q = query.trim();
  const intent = classifyIntent(query);
  const normalized = norm(query);
  const recency = opts.recencyScore ?? (() => 0);
  const max = opts.maxResults ?? 12;

  const items: SearchItem[] = [];

  // ── 1. Registry exact (indicators, curated instruments, aliases) ─────────
  const regExact = getInstrumentByAlias(query);
  if (regExact) {
    items.push({ entity: regExact, score: 1001, match: 'exact' });
  }

  // ── 2. Universe exact symbol (O(1)) ──────────────────────────────────────
  const uniExact = getUniverseBySymbol(query);
  if (uniExact) {
    const e = universeRowToEntity(uniExact);
    items.push({ entity: e, score: 1000, match: 'exact' });
  }

  // ── 2b. Economic event (live calendar) — "next NFP", "CPI this month" ─────
  if (intent.intent === 'event' || intent.intent === 'indicator') {
    const ev = resolveEvent(query);
    if (ev) items.push({ entity: ev, score: 990, match: 'exact' });
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
    if (regExact && e.id === regExact.id) continue;
    const s = scoreEntity({ entity: e, query: normalized, currentTab: opts.currentTab, recencyScore: recency(e.id) });
    if (s > 0) {
      items.push({ entity: e, score: boostedScore(s, e, opts.currentTab, recency(e.id)), match: matchKind(s) });
      continue;
    }
    // Fuzzy fallback on the small static set (cheap, handles "Aplle").
    const f = fuzzyScore(e, normalized, 2);
    if (f > 0) items.push({ entity: e, score: f, match: 'fuzzy' });
  }

  // ── 4. Universe fuzzy (FlexSearch — fast) ────────────────────────────────
  // Only when the query is a plausible instrument query, to avoid polluting
  // page/action lookups with thousands of ticker rows.
  const isInstrumentQuery =
    intent.intent === 'entity' ||
    intent.intent === 'indicator' ||
    intent.intent === 'data' ||
    intent.intent === 'unknown';
  if (isInstrumentQuery && q.length >= 2) {
    const hits = searchUniverse(query, 6);
    for (const row of hits) {
      const sym = row.symbol.toLowerCase();
      if (sym === normalized || (regExact && regExact.symbol?.toLowerCase() === sym)) continue;
      const e = universeRowToEntity(row);
      // Prefix/symbol matches rank above fuzzy name matches.
      const isSymPrefix = row.symbol.toLowerCase().startsWith(normalized);
      const score = isSymPrefix ? 700 : 520;
      items.push({ entity: e, score: boostedScore(score, e, opts.currentTab), match: isSymPrefix ? 'prefix' : 'fuzzy' });
    }
  }

  // ── 5. Actions (command palette) ─────────────────────────────────────────
  const actions = getAllActions().filter((a) => {
    if (a.static && normalized.length < 2) return false;
    return (
      normalized.includes(a.title.toLowerCase()) ||
      a.keywords.some((k) => normalized.includes(k)) ||
      a.title.toLowerCase().includes(normalized)
    );
  });

  let primaryAction: SearchAction | undefined;
  if (intent.intent === 'action' && actions.length > 0) {
    primaryAction = actions[0];
    const actionItems: SearchItem[] = actions.map((a, i) => ({
      entity: {
        id: a.id,
        kind: 'action',
        title: a.title,
        keywords: a.keywords,
        icon: a.icon,
        destination: { tab: 'chat' },
      },
      score: 2000 - i,
      match: 'keyword',
    }));
    items.push(...actionItems);
  }

  // Sort: score desc, then title asc for stability.
  items.sort((a, b) => b.score - a.score || a.entity.title.localeCompare(b.entity.title));

  return {
    intent: intent.intent,
    items: items.slice(0, max),
    actions,
    primaryAction,
    symbol: extractSymbol(query),
    universeReady: !!getUniverseBySymbol(query) || isUniverseBuilt(),
  };
}

function matchKind(s: number): SearchItem['match'] {
  if (s >= 1000) return 'exact';
  if (s >= 600) return 'prefix';
  return 'keyword';
}

function isUniverseBuilt(): boolean {
  return isUniverseLoaded();
}
