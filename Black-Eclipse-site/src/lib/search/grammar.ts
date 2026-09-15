// ── Query grammar ───────────────────────────────────────────────────────────
// Scoped prefixes and field operators for the command center. Pure, offline and
// deterministic — the palette parses the raw query here before the resolver
// runs, so power users can narrow search without a separate UI:
//
//   > open portfolio        commands only
//   # BTC                   symbols/securities only
//   @ cpi                   economic indicators only
//   / portfolio             navigation/pages only
//   ~ aapl                  user-owned data (funds, strategies)
//   ?                       help card
//   kind:crypto aapl        field filter (also class:/market:/asset:)
//
// Everything that is not a prefix or a recognised operator is left in the text
// for the resolver to match normally.

import type { EntityKind } from './types';

export type Scope = 'all' | 'action' | 'symbol' | 'indicator' | 'page' | 'user' | 'help';

export interface ScopeMeta {
  scope: Scope;
  /** Trigger character (or empty for the default scope). */
  prefix: string;
  label: string;
  /** Placeholder shown while the scope is active. */
  placeholder: string;
  /** One-line hint for the help card. */
  hint: string;
}

/** Scopes offered by the syntax help card / scope switcher (excludes 'all'). */
export const SCOPES: ScopeMeta[] = [
  { scope: 'symbol', prefix: '#', label: 'Instruments', placeholder: 'Search instruments and symbols…', hint: 'Search instruments & symbols' },
  { scope: 'action', prefix: '>', label: 'Commands', placeholder: 'Search commands…', hint: 'Run a command' },
  { scope: 'indicator', prefix: '@', label: 'Indicators', placeholder: 'Search economic indicators…', hint: 'Search economic indicators' },
  { scope: 'page', prefix: '/', label: 'Pages', placeholder: 'Search pages…', hint: 'Go to a page' },
  { scope: 'user', prefix: '~', label: 'Your data', placeholder: 'Search your funds, strategies…', hint: 'Search your own data' },
  { scope: 'help', prefix: '?', label: 'Help', placeholder: 'Type ? to see search syntax…', hint: 'Show search syntax' },
];

export const DEFAULT_SCOPE: ScopeMeta = {
  scope: 'all',
  prefix: '',
  label: '',
  placeholder: 'Search instruments, indicators, pages…',
  hint: 'Search everything',
};

/** Fields accepted as `field:value` operators. */
export type OperatorField = 'kind' | 'class' | 'market' | 'asset';

export interface ParsedQuery {
  /** Scope selected by a leading prefix character. */
  scope: Scope;
  /** Query text with the prefix and operators removed. */
  text: string;
  /** Trimmed, lowercased operator values keyed by field. */
  filters: Partial<Record<OperatorField, string>>;
  /** True when the raw query is nothing but a help trigger. */
  showHelp: boolean;
}

const FIELD_ALIASES: Record<string, OperatorField> = {
  kind: 'kind',
  class: 'class',
  market: 'market',
  asset: 'asset',
  symbol: 'asset',
};

/** Entity kinds a scope restricts the results to. */
export function scopeKinds(scope: Scope): EntityKind[] | null {
  switch (scope) {
    case 'symbol':
      return ['security', 'instrument'];
    case 'action':
      return ['action'];
    case 'indicator':
      return ['indicator', 'event'];
    case 'page':
      return ['page', 'doc', 'report'];
    case 'user':
      return ['user'];
    default:
      return null;
  }
}

/**
 * Parse a raw query into scope + free text + field filters. Operator matching is
 * case-insensitive; values are lowercased. A bare prefix with no text returns
 * the scope with an empty `text` so the palette can show scope hints.
 */
export function parseQuery(raw: string): ParsedQuery {
  let scope: Scope = 'all';
  let body = raw;

  const first = body.trimStart();
  const prefix = first.charAt(0);
  const match = SCOPES.find((s) => s.prefix === prefix);
  if (match) {
    scope = match.scope;
    const start = body.indexOf(prefix);
    body = body.slice(start + 1);
  }

  const filters: Partial<Record<OperatorField, string>> = {};
  const tokens = body.split(/\s+/);
  const kept: string[] = [];
  for (const tok of tokens) {
    const m = tok.match(/^([a-zA-Z]+):(.+)$/);
    const field = m ? FIELD_ALIASES[m[1].toLowerCase()] : undefined;
    if (m && field) {
      filters[field] = m[2].toLowerCase();
    } else {
      kept.push(tok);
    }
  }

  const text = kept.join(' ').trim();
  const showHelp = scope === 'help' && text.length === 0;

  return { scope, text, filters, showHelp };
}

/** True when an entity passes the parsed field filters. */
export function matchesFilters(
  entity: { kind: EntityKind; assetClass?: string; market?: string; symbol?: string },
  filters: ParsedQuery['filters'],
): boolean {
  const { kind, class: klass, market, asset } = filters;

  if (kind) {
    const allowed = kind.split(',').map((k) => k.trim());
    if (!allowed.includes(entity.kind)) return false;
  }
  if (klass && (entity.assetClass ?? '').toLowerCase() !== klass) return false;
  if (market && (entity.market ?? '').toLowerCase() !== market) return false;
  if (asset) {
    const sym = (entity.symbol ?? '').toLowerCase();
    if (sym !== asset && !sym.startsWith(asset)) return false;
  }
  return true;
}

/** Human-readable name for the current scope, for the palette chip. */
export function scopeLabel(scope: Scope): string {
  return SCOPES.find((s) => s.scope === scope)?.label ?? '';
}
