'use client';

// ── Capability Studio · Integrations section ────────────────────────────────
// A READ-ONLY summary of the operator's connected data: custom REST data
// sources (`/api/data-sources`, read-only GET) and MCP servers
// (`listMCPServers`). Create / edit / enable actions stay in their own
// operator surfaces (Settings → Data Sources, Settings → MCP Servers), which
// this section navigates to. Nothing here mutates a connection, and a load
// failure is shown as a failure — never as "nothing connected".

import { useCallback, useEffect, useState } from 'react';
import { Globe, RefreshCw } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import type { MCPListResponse } from '@/lib/harness/mcp-types';

// Client-safe: this module must never import `@/lib/harness/mcp-client`
// (server-only — child_process/fs). The Next.js route proxies to Python.
async function fetchMCPServers(): Promise<MCPListResponse> {
  const res = await fetch('/api/harness/mcp/servers', { cache: 'no-store' });
  const body = (await res.json().catch(() => ({}))) as MCPListResponse & { error?: string };
  if (!res.ok) throw new Error(body.error ?? `MCP list failed (HTTP ${res.status})`);
  return body;
}

/** The public connector shape the read-only GET returns (secrets omitted). */
export interface ConnectorView {
  id: string;
  name: string;
  enabled: boolean;
  capabilities: string[];
  health: { state?: string | null };
}

export interface ConnectorCounts {
  total: number;
  enabled: number;
  attention: number;
}

// `CONNECTED` is healthy; an untested (`UNKNOWN`/absent) connector is not an
// incident, but any recorded failing state is attention the operator owes.
const FAILING_STATES: ReadonlySet<string> = new Set(['ERROR', 'AUTH_FAILED', 'RATE_LIMITED', 'UNAVAILABLE']);

export function summarizeConnectors(connectors: ConnectorView[]): ConnectorCounts {
  const counts: ConnectorCounts = { total: connectors.length, enabled: 0, attention: 0 };
  for (const connector of connectors) {
    if (connector.enabled) counts.enabled += 1;
    if (connector.enabled && FAILING_STATES.has(String(connector.health?.state ?? ''))) counts.attention += 1;
  }
  return counts;
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: 'attention' }) {
  return (
    <div className="glass-card-subtle rounded-xl border border-border/20 px-3 py-2.5">
      <div className={cn('font-mono text-lg tabular-nums', tone === 'attention' && value > 0 ? 'text-amber-300' : 'text-foreground')}>
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  );
}

export function IntegrationsSection({
  onOpenSettings,
}: {
  onOpenSettings: (section: 'data' | 'mcp') => void;
}) {
  const t = useT();
  const [connectors, setConnectors] = useState<ConnectorView[] | null>(null);
  const [mcp, setMcp] = useState<MCPListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    // Both surfaces are independent: one failing must not hide the other, so
    // each result is resolved separately and the error names what failed.
    const [sources, servers] = await Promise.allSettled([
      fetch('/api/data-sources', { cache: 'no-store' }).then((res) => res.json() as Promise<{ connectors?: ConnectorView[] }>),
      fetchMCPServers(),
    ]);
    if (sources.status === 'fulfilled') setConnectors(sources.value.connectors ?? []);
    if (servers.status === 'fulfilled') setMcp(servers.value);
    const failures: string[] = [];
    if (sources.status === 'rejected') failures.push(t('studio.integrations.sources').toLowerCase());
    if (servers.status === 'rejected') failures.push(t('studio.integrations.mcp').toLowerCase());
    setError(failures.length ? failures.join(', ') : null);
    setLoading(false);
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-xs text-muted-foreground">{t('studio.loading')}</p>;
  }

  const counts = summarizeConnectors(connectors ?? []);

  return (
    <div className="space-y-3">
      {error ? (
        <div className="glass-card-subtle rounded-xl border border-rose-500/20 px-3 py-2.5 text-xs text-rose-200">
          <p>{t('studio.loadFailed', { what: error, reason: 'runtime unavailable' })}</p>
          <button type="button" onClick={() => void load()} className="glass-button mt-2 rounded-lg px-3 py-1 text-[11px] text-foreground">
            {t('studio.retry')}
          </button>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <StatCard label={t('studio.integrations.sources')} value={counts.total} />
        <StatCard label={t('studio.integrations.ready')} value={counts.enabled} />
        <StatCard label={t('studio.integrations.attention')} value={counts.attention} tone="attention" />
        <StatCard label={t('studio.integrations.mcpTools')} value={mcp?.registeredTools ?? 0} />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="glass-card rounded-xl p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <Globe size={12} /> {t('studio.integrations.sources')}
            </h2>
            <div className="flex items-center gap-1.5">
              <button type="button" onClick={() => void load()} aria-label={t('studio.retry')} className="rounded-md p-1 text-muted-foreground hover:text-foreground">
                <RefreshCw size={12} />
              </button>
              <button type="button" onClick={() => onOpenSettings('data')} className="glass-button rounded-lg px-3 py-1 text-[11px] text-foreground">
                {t('studio.integrations.openData')}
              </button>
            </div>
          </div>
          {(connectors ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('studio.integrations.empty')}</p>
          ) : (
            <ul className="divide-y divide-border/15">
              {(connectors ?? []).slice(0, 8).map((connector) => (
                <li key={connector.id} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                  <span className="min-w-0 flex-1 truncate text-foreground">{connector.name}</span>
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{connector.capabilities.join(', ')}</span>
                  <span
                    className={cn(
                      'shrink-0 rounded-full border px-1.5 py-px font-mono text-[9px] uppercase tracking-wide',
                      !connector.enabled
                        ? 'border-border/30 text-muted-foreground'
                        : FAILING_STATES.has(String(connector.health?.state ?? ''))
                          ? 'border-amber-500/25 bg-amber-500/10 text-amber-300'
                          : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300',
                    )}
                  >
                    {connector.enabled ? connector.health?.state ?? 'OK' : 'DISABLED'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="glass-card rounded-xl p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t('studio.integrations.mcp')} · {t('studio.integrations.mcpConnected')} {mcp?.connected ?? 0}/{mcp?.configured ?? 0}
            </h2>
            <button type="button" onClick={() => onOpenSettings('mcp')} className="glass-button rounded-lg px-3 py-1 text-[11px] text-foreground">
              {t('studio.integrations.openMcp')}
            </button>
          </div>
          {(mcp?.servers ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('studio.integrations.empty')}</p>
          ) : (
            <ul className="divide-y divide-border/15">
              {(mcp?.servers ?? []).slice(0, 8).map((server) => (
                <li key={server.id} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                  <span className="min-w-0 flex-1 truncate text-foreground">{server.name || server.id}</span>
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{server.transport}</span>
                  <span
                    className={cn(
                      'shrink-0 rounded-full border px-1.5 py-px font-mono text-[9px] uppercase tracking-wide',
                      !server.enabled
                        ? 'border-border/30 text-muted-foreground'
                        : server.untrusted
                          ? 'border-amber-500/25 bg-amber-500/10 text-amber-300'
                          : 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300',
                    )}
                  >
                    {!server.enabled ? 'DISABLED' : server.trust}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
