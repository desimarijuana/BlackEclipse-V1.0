// ── Investor Eye — DataHub topics ────────────────────────────────────────────
// Registers the Investor Eye topics once at module load. Consumers use
// `useTopic`/`useRefreshAll`; the hub batches, TTL-caches and fans out, and a
// failed topic becomes UNAVAILABLE without taking down the globe.
//
// Topics are keyed by time window so switching the timeline fetches once per
// window and repeated switches are instant.

'use client';

import { registerTopic, jsonTopic, type HubTopic } from '@/lib/workspace/data-hub';
import type { InvestorEyeState } from './types';

export const IE_STATE_TOPIC = 'investor-eye:state';
export const IE_HEALTH_TOPIC = 'investor-eye:health';

const stateTtl = 3 * 60_000;
const stateInterval = 3 * 60_000;

/** Register (idempotently) the state topic for a given window. */
export function registerStateTopic(hours: number): string {
  const id = `${IE_STATE_TOPIC}:${hours}`;
  registerTopic(
    jsonTopic<InvestorEyeState>(id, `/api/investor-eye/state?hours=${hours}`, {
      ttl: stateTtl,
      interval: stateInterval,
    }),
  );
  return id;
}

registerStateTopic(24);
registerStateTopic(1);
registerStateTopic(6);
registerStateTopic(168);
registerStateTopic(720);

registerTopic(
  jsonTopic(IE_HEALTH_TOPIC, '/api/investor-eye/health', { ttl: 60_000, interval: 120_000 }),
);

/** Economy layer topic (per metric). */
export function registerEconomyTopic(metric: string): string {
  const id = `investor-eye:economy:${metric}`;
  registerTopic(
    jsonTopic(id, `/api/investor-eye/economy?metric=${encodeURIComponent(metric)}`, {
      ttl: 30 * 60_000,
      interval: 0,
    }),
  );
  return id;
}

/** Companies layer topic (registered lazily — it is a Phase 2 layer). */
export const IE_COMPANIES_TOPIC = 'investor-eye:companies';
registerTopic(jsonTopic(IE_COMPANIES_TOPIC, '/api/investor-eye/companies?limit=250', { ttl: 15 * 60_000, interval: 0 }));

/** Risk topic (Phase 2). */
export const IE_RISK_TOPIC = 'investor-eye:risk';
registerTopic(jsonTopic(IE_RISK_TOPIC, '/api/investor-eye/risk?hours=24', { ttl: 5 * 60_000, interval: 0 }));

export type { HubTopic };
