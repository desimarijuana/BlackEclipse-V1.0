// ── Broker source (server-only) ──────────────────────────────────────────────
// The journal never talks to a broker directly. It asks the Python harness for
// the reconciled mirror: the operator-token-protected `/trading/*` routes. That
// keeps credentials, IPC sessions and the broker's own truth in one place.
//
// Everything here is read-only. A sync refreshes the mirror, and the projection
// reads it back; nothing in this module places, cancels or modifies an order.

import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import type { BrokerDeal, BrokerOpenPosition } from "./project";

export class BrokerSourceUnavailable extends Error {
  code: "RUNTIME_UNAVAILABLE" | "BROKER_UNAVAILABLE" | "REQUEST_FAILED";

  constructor(code: BrokerSourceUnavailable["code"], message: string) {
    super(message);
    this.name = "BrokerSourceUnavailable";
    this.code = code;
  }
}

export interface BrokerSyncState {
  connectionId: string;
  lastSyncedAt: string | null;
  lastDealAt: number | null;
  status: string;
  error: string | null;
  positionsCount: number;
  fillsAdded: number;
  updatedAt: string | null;
}

export interface BrokerMirror {
  connectionId: string;
  state: BrokerSyncState | null;
  deals: BrokerDeal[];
  positions: BrokerOpenPosition[];
}

export interface BrokerSyncResult {
  ok: boolean;
  connectionId: string;
  positions?: number;
  workingOrders?: number;
  fillsAdded?: number;
  ordersUpdated?: number;
  lastDealAt?: number;
  error?: unknown;
}

const TIMEOUT_MS = 45_000;

async function runtimeRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new BrokerSourceUnavailable(
      "RUNTIME_UNAVAILABLE",
      "The Python agent runtime is not available, so the broker mirror cannot be read.",
    );
  }
  const operatorToken = runtimeCallbackToken();
  let res: Response;
  try {
    res = await fetch(`${HARNESS_PY_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
        ...(init.headers ?? {}),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    throw new BrokerSourceUnavailable(
      "RUNTIME_UNAVAILABLE",
      err instanceof Error ? err.message : "broker runtime request failed",
    );
  }
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new BrokerSourceUnavailable(
      "REQUEST_FAILED",
      String(body.error ?? body.detail ?? `runtime HTTP ${res.status}`),
    );
  }
  return body as T;
}

function toDeal(row: Record<string, unknown>): BrokerDeal {
  return {
    dealTicket: Number(row.dealTicket ?? 0),
    orderTicket: row.orderTicket == null ? null : Number(row.orderTicket),
    positionTicket: row.positionTicket == null ? null : Number(row.positionTicket),
    symbol: String(row.symbol ?? ""),
    side: String(row.side ?? ""),
    entry: row.entry == null ? null : String(row.entry),
    volume: Number(row.volume ?? 0),
    price: Number(row.price ?? 0),
    commission: Number(row.commission ?? 0),
    swap: Number(row.swap ?? 0),
    profit: Number(row.profit ?? 0),
    magic: Number(row.magic ?? 0),
    comment: row.comment == null ? null : String(row.comment),
    dealtAt: Number(row.dealtAt ?? 0),
  };
}

function toPosition(row: Record<string, unknown>): BrokerOpenPosition {
  return {
    ticket: Number(row.ticket ?? 0),
    symbol: String(row.symbol ?? ""),
    side: String(row.side ?? ""),
    volume: Number(row.volume ?? 0),
    openPrice: Number(row.openPrice ?? 0),
    currentPrice: Number(row.currentPrice ?? 0),
    stopLoss: row.stopLoss == null ? null : Number(row.stopLoss),
    takeProfit: row.takeProfit == null ? null : Number(row.takeProfit),
    profit: Number(row.profit ?? 0),
    swap: Number(row.swap ?? 0),
    magic: Number(row.magic ?? 0),
    comment: row.comment == null ? null : String(row.comment),
    openedAt: Number(row.openedAt ?? 0),
  };
}

export interface BrokerConnectionSummary {
  id: string;
  kind: string;
  label: string;
  mode: string;
  status: string;
  statusReason?: string | null;
}

/**
 * Verify a broker connection exists before a journal link is created. A link
 * to a typo is a dead relationship; refusing it at creation is better than
 * discovering it on the first sync.
 */
export async function getBrokerConnection(connectionId: string): Promise<BrokerConnectionSummary> {
  const body = await runtimeRequest<{ connection?: BrokerConnectionSummary }>(
    `/trading/connections/${encodeURIComponent(connectionId)}`,
  );
  if (!body.connection) {
    throw new BrokerSourceUnavailable("REQUEST_FAILED", "Broker connection not found");
  }
  return body.connection;
}

/**
 * Refresh the broker's reconciled mirror. A failed sync is an honest error;
 * the caller keeps the last good projection.
 */
export async function syncBrokerMirror(
  connectionId: string,
  options: { days?: number } = {},
): Promise<BrokerSyncResult> {
  const days =
    options.days != null && Number.isFinite(options.days)
      ? Math.max(1, Math.min(3650, Math.round(options.days)))
      : null;
  const body = await runtimeRequest<Record<string, unknown>>(
    `/trading/connections/${encodeURIComponent(connectionId)}/sync`,
    {
      method: "POST",
      body: JSON.stringify(days ? { days } : {}),
    },
  );
  return body as unknown as BrokerSyncResult;
}

/**
 * Read the broker's reconciled mirror.
 *
 * Fills are paged oldest→newest-adjacent with a `(dealtAt, id)` cursor, so a
 * backfill beyond one page is complete rather than silently truncated. Twenty
 * pages of 1,000 is the hard bound (20,000 deals); a broker history larger than
 * that is beyond this surface's scope and is reported as a warning by the
 * caller's `skippedDeals`/count mismatch rather than invented.
 */
export async function readBrokerMirror(connectionId: string, pageSize = 1000): Promise<BrokerMirror> {
  const perPage = Math.max(1, Math.min(5000, Math.floor(pageSize)));
  const meta = await runtimeRequest<{
    available?: boolean;
    state?: BrokerSyncState | null;
    positions?: Record<string, unknown>[];
    error?: { code?: string; message?: string };
  }>(
    `/trading/connections/${encodeURIComponent(connectionId)}/reconciliation?limit=1`,
  );

  if (meta.available === false) {
    throw new BrokerSourceUnavailable(
      "BROKER_UNAVAILABLE",
      meta.error?.message || "The broker mirror is unavailable.",
    );
  }
  // The mirror may exist from a previous good sync while the broker itself is
  // down. Preview must say so rather than presenting stale rows as current.
  if (meta.state && (meta.state.status === "unavailable" || meta.state.status === "error")) {
    throw new BrokerSourceUnavailable(
      "BROKER_UNAVAILABLE",
      meta.state.error || "The broker is not available; showing no live mirror.",
    );
  }

  const deals: BrokerDeal[] = [];
  const base = `/trading/connections/${encodeURIComponent(connectionId)}/fills`;
  let beforeDealtAt: number | null = null;
  let beforeId: number | null = null;

  for (let page = 0; page < 20; page += 1) {
    const query = new URLSearchParams({ limit: String(perPage) });
    if (beforeDealtAt != null && beforeId != null) {
      query.set("beforeDealtAt", String(beforeDealtAt));
      query.set("beforeId", String(beforeId));
    }
    const body = await runtimeRequest<{ fills?: Record<string, unknown>[] }>(
      `${base}?${query.toString()}`,
    );
    const rows = body.fills ?? [];
    deals.push(...rows.map(toDeal));
    if (rows.length < perPage) break;

    const last = rows[rows.length - 1];
    const lastAt = Number(last.dealtAt ?? NaN);
    const lastId = Number(last.id ?? NaN);
    if (!Number.isFinite(lastAt) || !Number.isFinite(lastId)) break;
    beforeDealtAt = lastAt;
    beforeId = lastId;
  }

  return {
    connectionId,
    state: meta.state ?? null,
    positions: (meta.positions ?? []).map(toPosition),
    deals,
  };
}
