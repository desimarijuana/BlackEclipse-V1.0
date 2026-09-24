'use client';

// ── Market Regime client hook ────────────────────────────────────────────────
// One subscription over DataHub for the active scope. The topic id encodes the
// scope + market so switching markets yields independent caching/refresh, and
// the topic is (idempotently) registered on the fly.

import { useMemo } from 'react';
import { useTopic, registerTopic, jsonTopic, type HubEntry } from '@/lib/workspace/data-hub';
import type { RegimeResult, RegimeScope } from './types';
import { resolveRegimeMarket } from './scoring';
import { useRegimeScopeStore, useHydrateRegimeScope } from './store';
import { resolveUserMarket } from '@/lib/user-market';

export interface UseRegime {
  entry: HubEntry<RegimeResult>;
  result: RegimeResult | null;
  scope: RegimeScope;
  market: string;
  topicId: string;
}

/**
 * Subscribe to the regime reading for the current scope. `selected` resolves to
 * the user's active market (user-market store), so the glow follows the market
 * the user is actually looking at instead of always reading US.
 */
export function useRegime(): UseRegime {
  useHydrateRegimeScope();
  const scope = useRegimeScopeStore((s) => s.scope);

  const market = useMemo(
    () => resolveRegimeMarket(scope, scope === 'selected' ? resolveUserMarket() : null),
    [scope],
  );

  const topicId = `regime:${scope}:${market}`;
  // Register during render (idempotent) so the hub has the definition before
  // `useTopic` subscribes on mount and kicks the first fetch.
  useMemo(() => {
    registerTopic(
      jsonTopic<RegimeResult>(topicId, `/api/regime?scope=${scope}&market=${encodeURIComponent(market)}`, {
        ttl: 60_000,
        interval: 60_000,
      }),
    );
    return topicId;
  }, [topicId, scope, market]);

  const entry = useTopic<RegimeResult>(topicId);
  const result = entry.data && Array.isArray(entry.data.components) ? entry.data : null;
  return { entry, result, scope, market, topicId };
}
