'use client';

// ─── Shared broker snapshot ─────────────────────────────────────────────────
// One shared read path for every broker-backed surface (Command Center
// widgets, the Home trading section). Reads hit the SAME `/api/trading`
// connection the Settings panel owns; a missing connection renders an honest
// setup/empty state, never fake positions or fills.
//
// Broker reads are synchronous IPC on the Python side, so five consumers must
// not open five sets of MT5 sessions: a module-level snapshot with a 10s
// dedupe window serves everyone, and each mounted consumer polls on 15s.

import { useCallback, useEffect, useState } from 'react';
import {
  getBrokerAccount,
  getBrokerFills,
  getBrokerOrders,
  getBrokerPositions,
  listBrokerConnections,
  type BrokerAccount,
  type BrokerConnection,
  type BrokerEnvelope,
  type BrokerFill,
  type BrokerPosition,
  type BrokerWorkingOrder,
} from '@/lib/harness/trading-client';

export interface BrokerSnapshot {
  connection: BrokerConnection | null;
  account: BrokerAccount | null;
  positions: BrokerPosition[];
  orders: BrokerWorkingOrder[];
  fills: BrokerFill[];
  error: string | null;
}

export interface BrokerSnapshotState extends BrokerSnapshot {
  loading: boolean;
  refresh: () => Promise<void>;
}

let sharedSnapshot: { at: number; promise: Promise<BrokerSnapshot> } | null = null;

// The front door cold-starts the Python runtime on the first broker read,
// which can legitimately take tens of seconds. Never let the UI spin
// forever: surface an honest "still starting / unreachable" state instead.
const SNAPSHOT_TIMEOUT_MS = 25_000;

const TIMEOUT_SNAPSHOT: BrokerSnapshot = {
  connection: null,
  account: null,
  positions: [],
  orders: [],
  fills: [],
  error: 'Broker read timed out — the agent runtime may still be starting. Try again shortly.',
};

function withTimeout(promise: Promise<BrokerSnapshot>): Promise<BrokerSnapshot> {
  return Promise.race([
    promise,
    new Promise<BrokerSnapshot>((resolve) => {
      setTimeout(() => resolve(TIMEOUT_SNAPSHOT), SNAPSHOT_TIMEOUT_MS);
    }),
  ]);
}

async function loadSnapshot(): Promise<BrokerSnapshot> {
  try {
    const connections = await listBrokerConnections();
    const first =
      connections.find((candidate) => candidate.status === 'connected') ?? connections[0] ?? null;
    if (!first) {
      return { connection: null, account: null, positions: [], orders: [], fills: [], error: null };
    }
    const [accountBody, positionsBody, ordersBody, fillRows] = await Promise.all([
      getBrokerAccount(first.id).catch((err: unknown): BrokerEnvelope<BrokerAccount> => ({
        available: false,
        status: 'UNAVAILABLE' as const,
        connectionId: first.id,
        kind: first.kind,
        mode: first.mode,
        error: { code: 'FETCH_FAILED', message: err instanceof Error ? err.message : 'account read failed' },
      })),
      getBrokerPositions(first.id).catch((err: unknown): BrokerEnvelope<BrokerPosition[]> => ({
        available: false,
        status: 'UNAVAILABLE' as const,
        connectionId: first.id,
        kind: first.kind,
        mode: first.mode,
        error: { code: 'FETCH_FAILED', message: err instanceof Error ? err.message : 'positions read failed' },
      })),
      getBrokerOrders(first.id).catch((err: unknown): BrokerEnvelope<BrokerWorkingOrder[]> => ({
        available: false,
        status: 'UNAVAILABLE' as const,
        connectionId: first.id,
        kind: first.kind,
        mode: first.mode,
        error: { code: 'FETCH_FAILED', message: err instanceof Error ? err.message : 'orders read failed' },
      })),
      getBrokerFills(first.id, 200).catch(() => null as BrokerFill[] | null),
    ]);
    const failure =
      (!accountBody?.available && accountBody?.error?.message) ||
      (!positionsBody?.available && positionsBody?.error?.message) ||
      (!ordersBody?.available && ordersBody?.error?.message) ||
      (fillRows === null ? 'fills read failed' : null) ||
      null;
    return {
      connection: first,
      account: accountBody?.available ? accountBody.data ?? null : null,
      positions: positionsBody?.available ? positionsBody.data ?? [] : [],
      orders: ordersBody?.available ? ordersBody.data ?? [] : [],
      fills: fillRows ?? [],
      error: failure || null,
    };
  } catch (err) {
    return {
      connection: null,
      account: null,
      positions: [],
      orders: [],
      fills: [],
      error: err instanceof Error ? err.message : 'broker unavailable',
    };
  }
}

function fetchSnapshot(): Promise<BrokerSnapshot> {
  if (sharedSnapshot && Date.now() - sharedSnapshot.at < 10_000) {
    return sharedSnapshot.promise;
  }
  const promise = loadSnapshot();
  sharedSnapshot = { at: Date.now(), promise };
  return promise;
}

/** Drop the shared read cache after an action so the next read is fresh. */
export function invalidateBrokerSnapshot(): void {
  sharedSnapshot = null;
}

export function useBrokerSnapshot(): BrokerSnapshotState {
  const [snapshot, setSnapshot] = useState<BrokerSnapshot | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const next = await withTimeout(fetchSnapshot());
    setSnapshot(next);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return {
    connection: snapshot?.connection ?? null,
    account: snapshot?.account ?? null,
    positions: snapshot?.positions ?? [],
    orders: snapshot?.orders ?? [],
    fills: snapshot?.fills ?? [],
    error: snapshot?.error ?? null,
    loading,
    refresh,
  };
}
