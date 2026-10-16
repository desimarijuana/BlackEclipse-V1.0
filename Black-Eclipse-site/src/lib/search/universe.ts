// ── Universe index (client) ────────────────────────────────────────────────
// Fetches the compact JDDS snapshot once, builds an in-memory FlexSearch index
// over symbols + names, and serves sub-millisecond fuzzy/prefix lookups. The
// payload is cached in sessionStorage (keyed by version) so revisits skip the
// network entirely. No LLM, no per-keystroke I/O.

import type { SearchEntity } from './types';

// FlexSearch 0.7 runtime exposes a named `Index` constructor (runtime has it,
// but the bundled TS types only declare the default `FlexSearch` class with
// `create`). It is DYNAMICALLY imported: the root layout pulls this module in
// on every route (`search/store` → `universe`), but the library is only needed
// once the command-center palette first loads the universe — so a static import
// put the whole FlexSearch bundle on the initial critical path for no reason.

/** FlexSearch 0.7 `Index` — numeric id + string content. */
interface FlexIndexImpl {
  add(id: number, content: string): void;
  search(query: string, limit?: number): number[];
}

/** Wrapper combining the symbol + name indices under one search. */
interface FlexIndex {
  add(id: number, content: string): void;
  search(query: string, limit?: number): number[];
}

type FlexCtor = new (opts: { tokenize: string; cache: boolean }) => FlexIndexImpl;

let flexCtorPromise: Promise<FlexCtor> | null = null;

function getFlexIndexCtor(): Promise<FlexCtor> {
  if (!flexCtorPromise) {
    flexCtorPromise = import('flexsearch').then((mod) => {
      const m = mod as unknown as { Index?: FlexCtor; default?: { Index?: FlexCtor } & FlexCtor };
      const ctor = m.default?.Index ?? m.Index ?? m.default;
      if (!ctor) throw new Error('flexsearch Index constructor not found');
      return ctor;
    });
  }
  return flexCtorPromise;
}

export interface UniverseRow {
  id: number;
  symbol: string;
  name: string;
  market: string;
  assetClass: string;
}

interface UniversePayload {
  version: string;
  count: number;
  builtAt: number;
  symbols: string[];
  names: string[];
  markets: string[];
  classes: string[];
}

const STORAGE_KEY = 'black-eclipse:universe-index';
const INDEX_VERSION = '2.0.0';

let doc: FlexIndex | null = null;
let rows: UniverseRow[] = [];
let bySymbol: Map<string, UniverseRow> | null = null;
let loading: Promise<void> | null = null;
let loadError: Error | null = null;

/** Build the FlexSearch index (two fields: symbol + name) from a payload. */
async function buildIndex(payload: UniversePayload): Promise<void> {
  const FlexIndexCtor = await getFlexIndexCtor();
  const idx = new FlexIndexCtor({ tokenize: 'forward', cache: true });
  const nameIdx = new FlexIndexCtor({ tokenize: 'forward', cache: true });
  doc = { add: idx.add.bind(idx), search: (q: string, limit?: number) => {
    const symHits = (idx.search(q, limit) as number[]) || [];
    const nameHits = (nameIdx.search(q, limit) as number[]) || [];
    return [...symHits, ...nameHits];
  } };

  rows = [];
  bySymbol = new Map();
  const n = payload.symbols.length;
  for (let i = 0; i < n; i++) {
    const row: UniverseRow = {
      id: i,
      symbol: payload.symbols[i],
      name: payload.names[i],
      market: payload.markets[i],
      assetClass: payload.classes[i],
    };
    rows.push(row);
    idx.add(i, row.symbol);
    nameIdx.add(i, row.name);
    if (!bySymbol.has(row.symbol)) bySymbol.set(row.symbol, row);
  }
}

function cachedPayload(): UniversePayload | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as UniversePayload;
    if (p.version !== INDEX_VERSION) return null;
    return p;
  } catch {
    return null;
  }
}

function cachePayload(p: UniversePayload): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* quota errors — ignore, rebuild next time */
  }
}

/** Ensure the index is loaded (from cache or network). Idempotent. */
export function loadUniverseIndex(): Promise<void> {
  if (doc) return Promise.resolve();
  if (loading) return loading;

  loading = (async () => {
    const cached = cachedPayload();
    if (cached && cached.count > 0) {
      try {
        await buildIndex(cached);
        return;
      } catch {
        /* corrupt cache — fall through to network */
      }
    }

    try {
      const res = await fetch('/api/search/index', { cache: 'no-store' });
      if (!res.ok) throw new Error(`index fetch ${res.status}`);
      const payload = (await res.json()) as UniversePayload;
      await buildIndex(payload);
      cachePayload(payload);
    } catch (err) {
      loadError = err instanceof Error ? err : new Error('failed to load universe');
      throw loadError;
    }
  })();

  loading.finally(() => {
    loading = null;
  });
  return loading;
}

export function isUniverseLoaded(): boolean {
  return !!doc;
}

export function universeCount(): number {
  return rows.length;
}

/**
 * Fuzzy/prefix search over the universe. Returns raw rows (not SearchEntity).
 * Returns [] when the index isn't loaded yet.
 */
export function searchUniverse(query: string, limit = 8): UniverseRow[] {
  if (!doc) return [];
  const q = query.trim();
  if (!q) return [];
  try {
    const hits = doc.search(q, limit * 2);
    const out: UniverseRow[] = [];
    const seen = new Set<number>();
    for (const id of hits) {
      if (seen.has(id)) continue;
      seen.add(id);
      const r = rows[id];
      if (r) out.push(r);
      if (out.length >= limit) break;
    }
    return out;
  } catch {
    return [];
  }
}

/** O(1) exact-symbol lookup — the fast path for typing "AAPL". */
export function getUniverseBySymbol(raw: string): UniverseRow | undefined {
  if (!bySymbol) return undefined;
  const key = raw.trim().toUpperCase();
  return bySymbol.get(key);
}

/** Wrap a universe row as a SearchEntity pointing at the chart tab. */
export function universeRowToEntity(row: UniverseRow): SearchEntity {
  return {
    id: `u-${row.id}-${row.symbol}`,
    kind: 'security',
    title: row.name,
    symbol: row.symbol,
    assetClass: mapAssetClass(row.assetClass),
    market: row.market,
    keywords: [row.name],
    destination: { tab: 'chart', params: { symbol: row.symbol } },
    subtitle: `${row.symbol} · ${row.market}`,
  };
}

function mapAssetClass(raw: string): SearchEntity['assetClass'] {
  switch (raw) {
    case 'crypto': return 'crypto';
    case 'etf': return 'etf';
    default: return 'equity';
  }
}
