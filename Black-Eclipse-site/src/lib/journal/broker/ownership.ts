// ── Broker ↔ user field ownership (pure) ────────────────────────────────────
// The broker owns execution facts; the user owns analysis. This is the single
// list that both the update path and its tests use, so a new field cannot be
// silently allowed through one and rejected by the other.

export const BROKER_OWNED_TRADE_FIELDS = [
  "symbol",
  "direction",
  "entry",
  "exit",
  "stopLoss",
  "takeProfit",
  "quantity",
  "entryTime",
  "exitTime",
  "commission",
  "fee",
] as const;

export type BrokerOwnedTradeField = (typeof BROKER_OWNED_TRADE_FIELDS)[number];

const BROKER_OWNED = new Set<string>(BROKER_OWNED_TRADE_FIELDS);

/** Names of broker-owned fields present in a PATCH body (empty = allowed). */
export function brokerOwnedFieldsIn(input: Record<string, unknown>): string[] {
  return Object.keys(input).filter((key) => BROKER_OWNED.has(key) && input[key] !== undefined);
}

/** Python broker connection ids are generated cuid-like tokens. */
export function isValidBrokerConnectionId(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value);
}
