// Market Data Layer client — the front-door proxy to the Python `/market/*`
// operator routes. One thin wrapper; no state, no store.

export interface MarketProviderRow {
  id: string;
  label: string;
  capabilities: string[];
  assetTypes: string[];
  realtime: boolean;
  historical: boolean;
  streaming: boolean;
  credentialRef: string | null;
  configured: boolean | null;
  implemented: boolean;
  rateLimit: { requestsPerMinute?: number | null; requestsPerDay?: number | null; concurrency: number; costTier: string };
  notes?: string | null;
}

export interface MarketProviderHealth {
  provider: string;
  successes: number;
  failures: number;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  breaker: { state: string; failures: number; threshold: number; retryAfterSeconds: number | null; trippedCount: number };
}

export interface MarketRateLimitRow {
  declared: { requestsPerMinute: number | null; requestsPerDay: number | null; concurrency: number; costTier: string };
  observed: { limit: number | null; used: number | null; remaining: number | null; windowSeconds: number | null; at: string | null };
  effectiveRequestsPerMinute: number | null;
  inflight: number;
  granted: number;
  denied: number;
  throttled429: number;
  cooldownRemainingS: number;
}

export interface MarketHealth {
  available: boolean;
  cache?: { entries: number; hits: number; misses: number; staleSkips: number; inflight: number };
  metrics?: Record<string, number>;
  providerMetrics?: {
    providers: Record<string, { calls: number; avgLatencyMs: number; lastLatencyMs: number; maxLatencyMs: number }>;
    rateLimits: Record<string, MarketRateLimitRow>;
  };
  config?: Record<string, unknown>;
  persistedHealth?: Array<Record<string, unknown>>;
  reason?: string;
}

export interface MarketQualityEvent {
  id: number;
  capability: string | null;
  symbol: string | null;
  provider: string | null;
  kind: string | null;
  severity: string | null;
  detail: string | null;
  createdAt: string;
}

export interface MarketStreamSnapshot {
  available: boolean;
  state?: string;
  provider?: string;
  subscriptions?: Array<{ id: string; provider: string; symbols: string[]; eventTypes: string[]; createdAt: string; queueDepth: number }>;
  metrics?: Record<string, number>;
  reason?: string;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`/api/harness/market/${path}`, { cache: "no-store" });
  return (await res.json()) as T;
}

export function fetchMarketProviders(): Promise<{ status?: string; providerCount?: number; implementedCount?: number; providers?: MarketProviderRow[]; available?: boolean }> {
  return getJson("providers");
}

export function fetchMarketHealth(): Promise<MarketHealth> {
  return getJson("health");
}

export function fetchMarketQuality(limit = 50): Promise<{ available: boolean; events?: MarketQualityEvent[] }> {
  return getJson(`quality?limit=${limit}`);
}

export function fetchMarketStream(): Promise<MarketStreamSnapshot> {
  return getJson("stream");
}

export async function subscribeMarketStream(symbols: string[], eventTypes: string[]): Promise<Record<string, unknown>> {
  const res = await fetch("/api/harness/market/stream/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols, eventTypes }),
  });
  return (await res.json()) as Record<string, unknown>;
}

export async function unsubscribeMarketStream(subscriptionId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`/api/harness/market/stream/unsubscribe?subscription_id=${encodeURIComponent(subscriptionId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  return (await res.json()) as Record<string, unknown>;
}
