'use client';

// ── BrokerSyncButton — sync the linked broker from the Trades toolbar ────────
// The Settings panel owns linking and mapping; this is the everyday action.
// It renders nothing when no enabled link exists, so the toolbar stays clean.

import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCw } from '@/lib/icons';
import { cn } from '@/lib/utils';

interface Link {
  id: string;
  connectionId: string;
  enabled: boolean;
  lastSyncedAt: string | null;
  lastSyncStatus: string;
  lastError: string | null;
}

interface SyncSummary {
  ok: boolean;
  imported: number;
  updated: number;
  unchanged: number;
  openPositions: number;
  error?: string;
}

function ago(iso: string | null): string {
  if (!iso) return 'never';
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return 'never';
  const mins = Math.max(0, Math.round((Date.now() - t) / 60_000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function BrokerSyncButton({ onSynced }: { onSynced?: () => void }) {
  const [links, setLinks] = useState<Link[]>([]);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; bad?: boolean } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/journal/broker/links');
      const data = await res.json();
      const active = ((data.links ?? []) as Link[]).filter((link) => link.enabled);
      setLinks(active);
      setSelected((prev) => (active.some((l) => l.connectionId === prev) ? prev : active[0]?.connectionId ?? ''));
    } catch {
      // The toolbar affordance is optional; a failed discovery stays silent.
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (links.length === 0) return null;
  const current = links.find((link) => link.connectionId === selected) ?? links[0];

  const sync = async (connectionId: string) => {
    setBusy(true);
    setNotice(null);
    try {
      const res = await fetch('/api/journal/broker/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connectionId }),
      });
      const data = (await res.json()) as SyncSummary;
      if (!res.ok || !data.ok) {
        setNotice({ text: data.error ?? 'Broker unavailable', bad: true });
      } else {
        setNotice({
          text:
            data.imported || data.updated
              ? `+${data.imported} new · ${data.updated} updated`
              : 'Up to date',
        });
        onSynced?.();
      }
      await load();
    } catch (err) {
      setNotice({ text: err instanceof Error ? err.message : 'Sync failed', bad: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      {links.length > 1 && (
        <select
          value={current.connectionId}
          onChange={(e) => setSelected(e.target.value)}
          className="max-w-[9rem] rounded-lg bg-background/60 border border-border/40 px-2 py-1.5 text-[11px] font-mono outline-none"
          title="Broker connection"
        >
          {links.map((link) => (
            <option key={link.connectionId} value={link.connectionId}>
              {link.connectionId.slice(0, 8)}
            </option>
          ))}
        </select>
      )}
      <button
        onClick={() => void sync(current.connectionId)}
        disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs font-semibold text-muted-foreground hover:text-primary hover:border-primary/40 transition-all cursor-pointer disabled:opacity-50"
        title={`Broker sync (last ${ago(current.lastSyncedAt)}${current.lastError ? ` · ${current.lastError}` : ''})`}
      >
        {busy ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
        Broker
      </button>
      <span
        className={cn(
          'hidden font-mono text-[10px] sm:inline',
          current.lastSyncStatus === 'ok' ? 'text-muted-foreground/70' : 'text-amber-300/80',
        )}
        title={current.lastError ?? undefined}
      >
        {current.lastSyncStatus === 'ok' ? ago(current.lastSyncedAt) : current.lastSyncStatus}
      </span>
      {notice && (
        <span
          className={cn(
            'hidden max-w-[14rem] truncate font-mono text-[10px] sm:inline',
            notice.bad ? 'text-amber-300/80' : 'text-emerald-400/80',
          )}
        >
          {notice.bad && <AlertTriangle size={10} className="mr-1 inline" />}
          {notice.text}
        </span>
      )}
    </div>
  );
}
