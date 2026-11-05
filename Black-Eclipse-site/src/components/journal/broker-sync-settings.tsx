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
  backfillDays: number | null;
  error?: string;
}

interface AccountOption {
  id: string;
  name: string;
}

interface Rule {
  id: string;
  connectionId: string | null;
  magic: number | null;
  commentMatch: string | null;
  symbolMatch: string | null;
  strategyId: string | null;
  setupId: string | null;
  tagNames: string[];
  priority: number;
}

interface Ref {
  id: string;
  name: string;
}

const EMPTY_RULE = {
  magic: '',
  commentMatch: '',
  symbolMatch: '',
  strategyId: '',
  setupId: '',
  tags: '',
  priority: '0',
};

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
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
  const [rules, setRules] = useState<Rule[]>([]);
  const [strategies, setStrategies] = useState<Ref[]>([]);
  const [setups, setSetups] = useState<Ref[]>([]);
  const [newRule, setNewRule] = useState(EMPTY_RULE);
  const [ruleBusy, setRuleBusy] = useState(false);
  const [ruleError, setRuleError] = useState<string | null>(null);

  const linkByConnection = useMemo(
    () => new Map(links.map((link) => [link.connectionId, link])),
    [links],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [conns, linksRes, rulesRes, strategiesRes, setupsRes] = await Promise.all([
        listBrokerConnections(),
        getJson<{ links?: BrokerLink[] }>('/api/journal/broker/links'),
        getJson<{ rules?: Rule[] }>('/api/journal/broker/rules'),
        getJson<{ strategies?: Ref[] }>('/api/journal/strategies'),
        getJson<{ setups?: Ref[] }>('/api/journal/setups'),
      ]);
      setConnections(conns);
      setRules(rulesRes.rules ?? []);
      setStrategies(strategiesRes.strategies ?? []);
      setSetups(setupsRes.setups ?? []);
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

  const runSync = async (connection: BrokerConnection, fullBackfill = false) => {
    setBusy(`sync:${connection.id}`);
    setMessage(null);
    try {
      const res = await fetch('/api/journal/broker/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connectionId: connection.id, fullBackfill }),
      });
      const data = (await res.json()) as SyncSummary;
      if (!res.ok) throw new Error((data as { error?: string }).error || 'Sync failed');
      if (!data.ok) {
        setMessage({ connectionId: connection.id, text: data.error ?? 'Broker unavailable', bad: true });
      } else {
        setMessage({
          connectionId: connection.id,
          text: [
            `${data.imported} new`,
            `${data.updated} updated`,
            `${data.unchanged} unchanged`,
            `${data.openPositions} open`,
            data.skippedDeals ? `${data.skippedDeals} skipped` : null,
            data.backfillDays ? `${data.backfillDays}d backfill` : null,
            data.warnings.length ? `${data.warnings.length} warning(s)` : null,
          ]
            .filter(Boolean)
            .join(' · '),
          bad: data.warnings.length > 0,
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

  const addRule = async () => {
    setRuleBusy(true);
    setRuleError(null);
    try {
      const tags = newRule.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await fetch('/api/journal/broker/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          magic: newRule.magic.trim() ? Number(newRule.magic) : null,
          commentMatch: newRule.commentMatch.trim() || null,
          symbolMatch: newRule.symbolMatch.trim() || null,
          strategyId: newRule.strategyId || null,
          setupId: newRule.setupId || null,
          tagNames: tags.length ? tags : null,
          priority: Number(newRule.priority) || 0,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'Failed to add rule');
      setNewRule(EMPTY_RULE);
      await load();
    } catch (err) {
      setRuleError(err instanceof Error ? err.message : 'Failed to add rule');
    } finally {
      setRuleBusy(false);
    }
  };

  const removeRule = async (id: string) => {
    setRuleBusy(true);
    setRuleError(null);
    try {
      const res = await fetch(`/api/journal/broker/rules/${id}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'Failed to delete rule');
      }
      await load();
    } catch (err) {
      setRuleError(err instanceof Error ? err.message : 'Failed to delete rule');
    } finally {
      setRuleBusy(false);
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

                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">
                      Backfill window (days)
                    </span>
                    <input
                      type="number"
                      min={7}
                      max={3650}
                      defaultValue={existing.backfillDays}
                      onBlur={(e) => {
                        const days = Number(e.target.value);
                        if (Number.isFinite(days) && days !== existing.backfillDays) {
                          void patch(connection.id, { backfillDays: days });
                        }
                      }}
                      className="w-24 rounded-lg bg-background/60 border border-border/40 px-2 py-1.5 text-[11px] font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </label>
                  <button
                    onClick={() => {
                      if (
                        confirm(
                          'Re-request the full backfill window from the broker? It can take a while, but it will not duplicate trades.',
                        )
                      ) {
                        void runSync(connection, true);
                      }
                    }}
                    disabled={isBusy}
                    className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1.5 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-all cursor-pointer disabled:opacity-50"
                    title="Re-request the full backfill window from the broker"
                  >
                    {isBusy && busy?.startsWith('sync') ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                    Full backfill
                  </button>
                </div>
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

      <div className="mt-2 rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2.5 flex flex-col gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
            Attribution rules
          </p>
          <p className="text-[10px] text-muted-foreground/70">
            Map magic / comment / symbol to a strategy, setup and tags. Rules apply on
            the next sync and only fill gaps — they never overwrite your own attribution.
          </p>
        </div>

        {rules.length > 0 && (
          <div className="flex flex-col gap-1">
            {rules.map((rule) => {
              const strategy = strategies.find((s) => s.id === rule.strategyId)?.name;
              const setup = setups.find((s) => s.id === rule.setupId)?.name;
              const matcher = [
                rule.magic != null ? `magic ${rule.magic}` : null,
                rule.commentMatch ? `comment ~ "${rule.commentMatch}"` : null,
                rule.symbolMatch ? `symbol ${rule.symbolMatch}` : null,
              ].filter(Boolean).join(' · ');
              return (
                <div
                  key={rule.id}
                  className="flex items-center justify-between gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2 py-1.5"
                >
                  <div className="min-w-0">
                    <p className="font-mono text-[10px] text-foreground truncate">
                      {matcher || 'no matcher'}
                      {rule.priority ? <span className="text-muted-foreground"> · p{rule.priority}</span> : null}
                    </p>
                    <p className="text-[10px] text-muted-foreground truncate">
                      {strategy || 'no strategy'} · {setup || 'no setup'}
                      {rule.tagNames.length > 0 ? ` · ${rule.tagNames.join(', ')}` : ''}
                    </p>
                  </div>
                  <button
                    onClick={() => void removeRule(rule.id)}
                    disabled={ruleBusy}
                    className="text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer disabled:opacity-50"
                    title="Delete rule"
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          <input
            value={newRule.magic}
            onChange={(e) => setNewRule({ ...newRule, magic: e.target.value })}
            placeholder="Magic"
            className="rounded-lg bg-background/60 border border-border/40 px-2 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-primary"
          />
          <input
            value={newRule.commentMatch}
            onChange={(e) => setNewRule({ ...newRule, commentMatch: e.target.value })}
            placeholder="Comment contains"
            className="rounded-lg bg-background/60 border border-border/40 px-2 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-primary"
          />
          <input
            value={newRule.symbolMatch}
            onChange={(e) => setNewRule({ ...newRule, symbolMatch: e.target.value })}
            placeholder="Symbol glob (XAU*)"
            className="rounded-lg bg-background/60 border border-border/40 px-2 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-primary"
          />
          <input
            value={newRule.priority}
            onChange={(e) => setNewRule({ ...newRule, priority: e.target.value })}
            placeholder="Priority"
            type="number"
            className="rounded-lg bg-background/60 border border-border/40 px-2 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-primary"
          />
          <select
            value={newRule.strategyId}
            onChange={(e) => setNewRule({ ...newRule, strategyId: e.target.value })}
            className="rounded-lg bg-background/60 border border-border/40 px-2 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">No strategy</option>
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <select
            value={newRule.setupId}
            onChange={(e) => setNewRule({ ...newRule, setupId: e.target.value })}
            className="rounded-lg bg-background/60 border border-border/40 px-2 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">No setup</option>
            {setups.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <input
            value={newRule.tags}
            onChange={(e) => setNewRule({ ...newRule, tags: e.target.value })}
            placeholder="Tags, comma separated"
            className="rounded-lg bg-background/60 border border-border/40 px-2 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-primary sm:col-span-2"
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => void addRule()}
            disabled={ruleBusy}
            className="inline-flex items-center gap-1 rounded-lg border border-primary/40 bg-primary/15 px-2 py-1 text-[10px] font-bold text-primary hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
          >
            {ruleBusy ? <Loader2 size={10} className="animate-spin" /> : <Link2 size={10} />}
            Add rule
          </button>
          {ruleError && <span className="text-[10px] text-amber-300/80">{ruleError}</span>}
        </div>
      </div>
    </div>
  );
}
