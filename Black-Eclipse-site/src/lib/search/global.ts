// ── Global search sources (client) ───────────────────────────────────────────
// Fetches server-side data (journal, news, reports) once and merges it into
// the resolver. Also provides a `registerSearchSource` hook so any future
// feature can contribute its own searchable entities without touching the
// resolver — the "search everything / whatever new thing we add" requirement.

import type { SearchEntity } from './types';

export interface GlobalEntityRow {
  id: string;
  kind: 'user' | 'report' | 'doc';
  title: string;
  keywords: string[];
  icon: string;
  tab: string;
  params?: Record<string, string>;
  deepLink?: string;
  subtitle: string;
}

// ── Auto-registration: features can push their own entity sources ─────────
type EntitySource = () => SearchEntity[] | Promise<SearchEntity[]>;
const sources: EntitySource[] = [];

/** Register a function that contributes searchable entities. */
export function registerSearchSource(fn: EntitySource): void {
  sources.push(fn);
}

let globalCache: SearchEntity[] | null = null;
let loading: Promise<void> | null = null;

function rowToEntity(r: GlobalEntityRow): SearchEntity {
  return {
    id: r.id,
    kind: r.kind,
    title: r.title,
    keywords: r.keywords,
    icon: r.icon,
    destination: {
      tab: r.tab as SearchEntity['destination']['tab'],
      params: r.params,
      ...(r.deepLink ? { deepLink: r.deepLink } : {}),
    },
    subtitle: r.subtitle,
  };
}

/** Fetch the server-side global entities once (idempotent). */
export function loadGlobalEntities(): Promise<void> {
  if (globalCache) return Promise.resolve();
  if (loading) return loading;
  loading = (async () => {
    const merged: SearchEntity[] = [];
    try {
      const res = await fetch('/api/search/global', { cache: 'no-store' });
      if (res.ok) {
        const d = await res.json();
        if (Array.isArray(d.entities)) {
          for (const r of d.entities as GlobalEntityRow[]) merged.push(rowToEntity(r));
        }
      }
    } catch {
      /* offline — fall through to registered sources only */
    }
    // Merge registered sources (may be async).
    for (const src of sources) {
      try {
        const ents = await src();
        if (Array.isArray(ents)) merged.push(...ents);
      } catch {
        /* ignore a failing source */
      }
    }
    globalCache = merged;
  })();
  loading.finally(() => { loading = null; });
  return loading;
}

export function isGlobalLoaded(): boolean {
  return globalCache !== null;
}

/** All global entities (empty until loaded). */
export function getGlobalEntities(): SearchEntity[] {
  return globalCache ?? [];
}
