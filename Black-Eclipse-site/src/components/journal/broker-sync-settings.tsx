'use client';

// ── BrokerSyncSettings — connect a broker connection to the journal ──────────
// A thin client over the journal broker API:
//   • list the broker connections the Python harness already knows about;
//   • link one to a journal account (or unlink it);
//   • preview and manually sync trades.
// It never talks to a broker directly and never displays a credential.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Link2,
  Loader2,
  Plug,
  RefreshCw,
  Unplug,
} from '@/lib/icons';
import { listBrokerConnections, type BrokerConnection } from '@/lib/harness/trading-client';
import { cn } from '@/lib/utils';

interface BrokerLink {
  id: string;
  connectionId: string;
  accountId: string | null;
  enabled: boolean;
  autoSync: boolean;
  backfillDays: number;
  lastSyncedAt: string | null;
  lastSyncStatus: string;
  lastError: string | null;
  symbolMap: Record<string, string>;
}

interface Preview {
  ok: boolean;
  willImport: number;
  willUpdate: number;
  ignored: number;
  totalProjected: number;
  openPositions: number;
  warnings: string[];
  error?: string;
}

interface SyncSummary {
  ok: boolean;
  imported: number;
  updated: number;
  unchanged: number;
  ignored: number;
  openPositions: number;
  totalProjected: number;
  skippedDeals: number;
  warnings: string[];
  error?: string;
}

interface AccountOption {
  id: string;
  name: string;
}

function fmtWhen(iso: string | null): string {
  if (!iso) return 'never';
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return 'never';
  return new Date(t).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function parseMapText(text: string): Record<string, string> {
  const map: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const [rawKey, ...rest] = line.split('=');
    if (!rawKey || rest.length === 0) continue;
    const key = rawKey.trim();
    const value = rest.join('=').trim();
    if (key && value) map[key] = value;
  }
  return map;
}

function mapToText(map: Record<string, string>): string {
  return Object.entries(map)
    .map(([key, value]) => `${key}=${value}`)
    .join('\n');
}

export function BrokerSyncSettings({ accounts }: { accounts: AccountOption[] }) {
  const [connections, setConnections] = useState<BrokerConnection[]>([]);
  const [links, setLinks] = useState<BrokerLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ connectionId: string; text: string; bad?: boolean } | null>(null);

  const [newAccount, setNewAccount] = useState<Record<string, string>>({});
  const [mapText, setMapText] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Record<string, Preview>>({});

  const linkByConnection = useMemo(
    () => new Map(links.map((link) => [link.connectionId, link])),
    [links],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [conns, linksRes] = await Promise.all([
        listBrokerConnections(),
        fetch('/api/journal/broker/links').then((r) => r.json()),
      ]);
      setConnections(conns);
      const nextLinks: BrokerLink[] = linksRes.links ?? [];
      setLinks(nextLinks);
      setMapText((prev) => {
        const next = { ...prev };
        for (const link of nextLinks) {
          if (next[link.connectionId] === undefined) next[link.connectionId] = mapToText(link.symbolMap);
        }
        return next;
      });
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Broker settings unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const link = async (connection: BrokerConnection) => {
    setBusy(`link:${connection.id}`);
    setMessage(null);
    try {
      const res = await fetch('/api/journal/broker/links', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connectionId: connection.id,
          accountId: newAccount[connection.id] || null,
          symbolMap: parseMapText(mapText[connection.id] ?? ''),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to link');
      setMessage({
        connectionId: connection.id,
        text: 'Linked. Preview reads the last broker sync; Sync refreshes it first.',
      });
      await load();
    } catch (err) {
      setMessage({
        connectionId: connection.id,
        text: err instanceof Error ? err.message : 'Failed to link',
        bad: true,
      });
    } finally {
      setBusy(null);
    }
  };

  const patch = async (connectionId: string, body: Record<string, unknown>) => {
    const existing = linkByConnection.get(connectionId);
    if (!existing) return;
    setBusy(`patch:${connectionId}`);
    try {
      const res = await fetch(`/api/journal/broker/links/${existing.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to update');
      await load();
    } catch (err) {
      setMessage({
        connectionId,
        text: err instanceof Error ? err.message : 'Failed to update',
        bad: true,
      });
    } finally {
      setBusy(null);
    }
  };

  const unlink = async (connection: BrokerConnection) => {
    const existing = linkByConnection.get(connection.id);
    if (!existing) return;
    if (!confirm('Unlink this broker from the journal? Imported trades are kept.')) return;
    setBusy(`unlink:${connection.id}`);
    try {
      const res = await fetch(`/api/journal/broker/links/${existing.id}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'Failed to unlink');
      }
      setPreview((prev) => {
        const next = { ...prev };
        delete next[connection.id];
        return next;
      });
      await load();
    } catch (err) {
      setMessage({
        connectionId: connection.id,
        text: err instanceof Error ? err.message : 'Failed to unlink',
        bad: true,
      });
    } finally {
      setBusy(null);
    }
  };

  const runPreview = async (connection: BrokerConnection) => {
    setBusy(`preview:${connection.id}`);
    setMessage(null);
    try {
      const res = await fetch(
        `/api/journal/broker/preview?connectionId=${encodeURIComponent(connection.id)}`,
      );
      const data = (await res.json()) as Preview;
      if (!res.ok) throw new Error((data as { error?: string }).error || 'Preview failed');
      setPreview((prev) => ({ ...prev, [connection.id]: data }));
      if (!data.ok) {
        setMessage({ connectionId: connection.id, text: data.error ?? 'Preview unavailable', bad: true });
      }
    } catch (err) {
      setMessage({
        connectionId: connection.id,
        text: err instanceof Error ? err.message : 'Preview failed',
        bad: true,
      });
    } finally {
      setBusy(null);
    }
  };

  const runSync = async (connection: BrokerConnection) => {
    setBusy(`sync:${connection.id}`);
    setMessage(null);
    try {
      const res = await fetch('/api/journal/broker/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connectionId: connection.id }),
      });
      const data = (await res.json()) as SyncSummary;
      if (!res.ok) throw new Error((data as { error?: string }).error || 'Sync failed');
      if (!data.ok) {
        setMessage({ connectionId: connection.id, text: data.error ?? 'Broker unavailable', bad: true });
      } else {
        setMessage({
          connectionId: connection.id,
          text: `${data.imported} new · ${data.updated} updated · ${data.unchanged} unchanged · ${data.openPositions} open`,
        });
      }
      await load();
    } catch (err) {
      setMessage({
        connectionId: connection.id,
        text: err instanceof Error ? err.message : 'Sync failed',
        bad: true,
      });
    } finally {
      setBusy(null);
    }
  };

  if (loading && connections.length === 0) {
    return (
      <p className="flex items-center gap-2 text-[11px] text-muted-foreground italic">
        <Loader2 size={12} className="animate-spin" /> Reading broker connections…
      </p>
    );
  }

  if (loadError) {
    return (
      <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200/80">
        <AlertTriangle size={12} className="inline mr-1.5" />
        {loadError}. The Python runtime and a configured broker connection are required.
      </div>
    );
  }

  if (connections.length === 0) {
    return (
      <p className="text-[11px] text-muted-foreground/70 italic">
        No broker connections yet. Add one from the broker button in the sidebar, then link it here.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {connections.map((connection) => {
        const existing = linkByConnection.get(connection.id);
        const isBusy = busy?.endsWith(`:${connection.id}`);
        const p = preview[connection.id];
        const notice = message?.connectionId === connection.id ? message : null;
        const connected = connection.status === 'connected';

        return (
          <div
            key={connection.id}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 flex flex-col gap-2"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-bold text-foreground truncate flex items-center gap-1.5">
                  <Plug size={12} className={connected ? 'text-emerald-400' : 'text-muted-foreground'} />
                  {connection.label}
                  <span className="font-mono text-[9px] font-normal text-muted-foreground">
                    {connection.kind} · {connection.mode}
                  </span>
                </p>
                <p className="font-mono text-[10px] text-muted-foreground">
                  {connection.account
                    ? `${connection.account.server || 'broker'} · ${connection.account.currency} ${connection.account.balance.toLocaleString()}`
                    : connection.statusReason || connection.status}
                  {existing ? ` · synced ${fmtWhen(existing.lastSyncedAt)}` : ''}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {existing ? (
                  <>
                    <button
                      onClick={() => void runPreview(connection)}
                      disabled={isBusy}
                      className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-all cursor-pointer disabled:opacity-50"
                      title="Preview without writing"
                    >
                      {isBusy && busy?.startsWith('preview') ? <Loader2 size={11} className="animate-spin" /> : <AlertTriangle size={11} />}
                      Preview
                    </button>
                    <button
                      onClick={() => void runSync(connection)}
                      disabled={isBusy}
                      className="inline-flex items-center gap-1 rounded-lg border border-primary/40 bg-primary/15 px-2 py-1 text-[11px] font-bold text-primary hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
                    >
                      {isBusy && busy?.startsWith('sync') ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                      Sync
                    </button>
                    <button
                      onClick={() => void unlink(connection)}
                      disabled={isBusy}
                      className="text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer disabled:opacity-50"
                      title="Unlink from the journal (keeps imported trades)"
                    >
                      <Unplug size={13} />
                    </button>
                  </>
                ) : (
                  <>
                    <select
                      value={newAccount[connection.id] ?? ''}
                      onChange={(e) =>
                        setNewAccount((prev) => ({ ...prev, [connection.id]: e.target.value }))
                      }
                      className="rounded-lg bg-background/60 border border-border/40 px-2 py-1 text-[11px] font-mono outline-none"
                    >
                      <option value="">No account</option>
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => void link(connection)}
                      disabled={isBusy}
                      className="inline-flex items-center gap-1 rounded-lg border border-primary/40 bg-primary/15 px-2 py-1 text-[11px] font-bold text-primary hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
                    >
                      {isBusy ? <Loader2 size={11} className="animate-spin" /> : <Link2 size={11} />}
                      Link journal
                    </button>
                  </>
                )}
              </div>
            </div>

            {existing && (
              <div className="flex flex-col gap-1.5">
                <div className="flex flex-wrap items-center gap-3">
                  <label className="inline-flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={existing.enabled}
                      onChange={(e) => void patch(connection.id, { enabled: e.target.checked })}
                      className="accent-primary"
                    />
                    Enabled
                  </label>
                  <label className="inline-flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={existing.autoSync}
                      onChange={(e) => void patch(connection.id, { autoSync: e.target.checked })}
                      className="accent-primary"
                    />
                    Auto-sync
                  </label>
                  <span
                    className={cn(
                      'font-mono text-[10px]',
                      existing.lastSyncStatus === 'ok' ? 'text-emerald-400/80' : 'text-amber-300/80',
                    )}
                  >
                    {existing.lastSyncStatus}
                    {existing.lastError ? ` · ${existing.lastError}` : ''}
                  </span>
                </div>
                <label className="flex flex-col gap-1">
                  <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">
                    Symbol map (broker = journal), one per line
                  </span>
                  <textarea
                    value={mapText[connection.id] ?? ''}
                    onChange={(e) => setMapText((prev) => ({ ...prev, [connection.id]: e.target.value }))}
                    onBlur={() => void patch(connection.id, { symbolMap: parseMapText(mapText[connection.id] ?? '') })}
                    rows={2}
                    placeholder={'EURUSD.a=EURUSD\nXAUUSDm=XAUUSD'}
                    className="w-full rounded-lg bg-background/60 border border-border/40 px-2 py-1.5 text-[11px] font-mono outline-none focus:ring-1 focus:ring-primary"
                  />
                </label>
              </div>
            )}

            {p && (
              <p className="font-mono text-[10px] text-muted-foreground">
                {p.ok
                  ? `Preview: ${p.willImport} new · ${p.willUpdate} update · ${p.ignored} ignored · ${p.openPositions} open`
                  : `Preview unavailable: ${p.error}`}
                {p.warnings.length > 0 ? ` · ${p.warnings.length} warning(s)` : ''}
              </p>
            )}

            {notice && (
              <p
                className={cn(
                  'font-mono text-[10px]',
                  notice.bad ? 'text-amber-300/80' : 'text-emerald-400/80',
                )}
              >
                {notice.bad ? <AlertTriangle size={10} className="inline mr-1" /> : <Check size={10} className="inline mr-1" />}
                {notice.text}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
