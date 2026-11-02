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

/**
 * Refresh the broker's reconciled mirror. A failed sync is an honest error;
 * the caller keeps the last good projection.
 */
export async function syncBrokerMirror(connectionId: string): Promise<BrokerSyncResult> {
  const body = await runtimeRequest<Record<string, unknown>>(
    `/trading/connections/${encodeURIComponent(connectionId)}/sync`,
    { method: "POST", body: "{}" },
  );
  return body as unknown as BrokerSyncResult;
}

/**
 * Read the broker's reconciled mirror.
 *
 * `limit` is clamped by the runtime to 500 deals. That covers the reconciler's
 * default window; a wider first backfill needs the history endpoint (Phase 2).
 */
export async function readBrokerMirror(connectionId: string, limit = 500): Promise<BrokerMirror> {
  const safeLimit = Math.max(1, Math.min(500, Math.floor(limit)));
  const body = await runtimeRequest<{
    available?: boolean;
    state?: BrokerSyncState | null;
    positions?: Record<string, unknown>[];
    fills?: Record<string, unknown>[];
    error?: { code?: string; message?: string };
  }>(
    `/trading/connections/${encodeURIComponent(connectionId)}/reconciliation?limit=${safeLimit}`,
  );

  if (body.available === false) {
    throw new BrokerSourceUnavailable(
      "BROKER_UNAVAILABLE",
      body.error?.message || "The broker mirror is unavailable.",
    );
  }

  return {
    connectionId,
    state: body.state ?? null,
    positions: (body.positions ?? []).map(toPosition),
    deals: (body.fills ?? []).map(toDeal),
  };
}
