// ── User-scoped entities (funds, strategies, etc.) ─────────────────────────
// Reads the user's localStorage-backed data (funds, journal strategies) and
// exposes them as searchable entities. These are resolved client-side from
// localStorage — no server round-trip, no LLM. The resolver merges them in.
//
// NOTE: deliberately NOT cached. The search bar mounts on app load, before the
// portfolio screen seeds funds into localStorage — a stale cache would hide
// funds forever. Funds are tiny, so reading fresh on each resolve is cheap.

import type { SearchEntity } from './types';

function loadFundsEntities(): SearchEntity[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem('be_portfolio_funds_v1');
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((f: unknown): f is { id: string; name: string } =>
        Boolean(f) && typeof (f as { id?: unknown }).id === 'string' && typeof (f as { name?: unknown }).name === 'string')
      .map((f) => ({
        id: `fund-${f.id}`,
        kind: 'user' as const,
        title: f.name,
        keywords: ['fund', 'portfolio', 'my fund', f.name.toLowerCase()],
        icon: 'briefcase',
        destination: { tab: 'portfolio' as const, params: { fund: f.id } },
        subtitle: 'Fund · Portfolio',
        rankBoost: 1.1,
      }));
  } catch {
    return [];
  }
}

/** Get the user's funds as searchable entities (read fresh each call). */
export function getUserEntities(): SearchEntity[] {
  return loadFundsEntities();
}
