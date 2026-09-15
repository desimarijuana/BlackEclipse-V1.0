// ── Capability resolver ─────────────────────────────────────────────────────
// Answers "who can satisfy this capability request?" — and never fabricates
// data. The resolver returns real connectors only; if none match it returns an
// empty list, and callers surface UNAVAILABLE. Route-level demo fallbacks stay
// in the routes that already have them.
//
// Precedence is deterministic and explicit:
//   1. existing scraper fetchers (callers try these first, outside this layer)
//   2. connector tier — built-ins, then operator-configured custom connectors
//
// No automatic cross-provider fallback (e.g. Binance → CoinGecko → Yahoo) is
// introduced here. Changing that ordering is a separate architectural decision.

import { listConnectors } from "./registry";
import type { Capability, DataConnector } from "./types";

export interface ResolveRequest {
  capability: Capability;
  /** Optional symbol; passed through to connectors but not used for filtering. */
  symbol?: string;
}

/** Lower rank = higher precedence. Built-ins outrank operator connectors. */
function rank(connector: DataConnector): number {
  return connector.kind === "builtin" ? 0 : 1;
}

/**
 * Resolve connectors for a capability, ordered by precedence.
 * Deterministic: ties break by connector id so results are stable across runs.
 */
export function resolveConnectors(request: ResolveRequest): DataConnector[] {
  return listConnectors()
    .filter((c) => c.capabilities.includes(request.capability) && c.isConfigured())
    .sort((a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id));
}

/** The single connector that would be tried first, or undefined. */
export function resolvePrimary(request: ResolveRequest): DataConnector | undefined {
  return resolveConnectors(request)[0];
}
