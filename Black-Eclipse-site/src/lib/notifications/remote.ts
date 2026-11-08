'use client';

// ─── Durable notification archive (client writer) ───────────────────────────
// The header notification ledger lives in localStorage so it is instant and
// available offline. Every write is ALSO mirrored to the DB through
// `POST /api/notifications`, so Alerts › History can search everything ever
// received and the archive survives clearing site data.
//
// Fire-and-forget by design: a failed archive write must never block the UI
// (offline, quota, server restart). The producer's stable id is the dedupe key,
// so retries are harmless.

export interface PersistableNotification {
  id: string;
  tab: string;
  kind: string;
  title: string;
  body: string;
  /** Epoch ms; omitted = server now. */
  at?: number;
  read?: boolean;
}

const MAX_BATCH = 100;

function send(items: readonly PersistableNotification[]): void {
  if (typeof window === 'undefined') return;
  if (!Array.isArray(items) || items.length === 0) return;
  try {
    void fetch('/api/notifications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: items.slice(0, MAX_BATCH) }),
      // Let the request finish even if the tab closes right after a raise.
      keepalive: true,
    }).catch(() => {
      /* offline / runtime down — the local ledger still has it */
    });
  } catch {
    /* fetch unavailable — ignore */
  }
}

export function persistNotificationRemote(item: PersistableNotification): void {
  send([item]);
}

/** Backfill a whole local ledger once (idempotent on the server). */
export function persistNotificationsRemote(items: readonly PersistableNotification[]): void {
  send(items);
}
