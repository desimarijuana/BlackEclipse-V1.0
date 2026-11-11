'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, Sparkles } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import { useCommandStore } from '@/lib/search/store';
import {
  activateCapability,
  deactivateCapability,
  listBuiltins,
  listCapabilities,
  promoteCapability,
  removeCapability,
  rollbackCapability,
  type BuiltinCapability,
  type CapabilityRecord,
  type CapabilityStatus,
} from '@/lib/harness/capabilities-client';
import { GapsSection } from './gaps-section';

const STATUS_KEY: Record<CapabilityStatus, TranslationKey> = {
  draft: 'capabilityCard.status.gap',
  unverified: 'capabilityCard.status.unverified',
  tested: 'capabilityCard.status.tested',
  approval_required: 'capabilityCard.status.approval_required',
  active: 'capabilityCard.status.active',
  disabled: 'capabilityCard.status.disabled',
  retired: 'capabilityCard.status.retired',
};

const TEST_KEY: Record<string, TranslationKey> = {
  verified: 'studio.generated.testVerified',
  failed: 'studio.generated.testFailed',
  unverified: 'studio.generated.testUnverified',
};

const ATTENTION: ReadonlySet<CapabilityStatus> = new Set([
  'unverified', 'approval_required', 'disabled',
]);

const ACTIONABLE: ReadonlySet<CapabilityStatus> = new Set([
  'tested', 'approval_required', 'disabled', 'active',
]);

export interface CapabilitySummaryCounts {
  total: number;
  active: number;
  attention: number;
  versions: number;
}

export function summarizeCapabilities(records: CapabilityRecord[]): CapabilitySummaryCounts {
  const latest = new Map<string, CapabilityRecord>();
  for (const record of records) {
    if (!latest.has(record.capabilityId)) latest.set(record.capabilityId, record);
  }
  let active = 0;
  let attention = 0;
  for (const record of latest.values()) {
    if (record.status === 'active') active += 1;
    if (ATTENTION.has(record.status)) attention += 1;
  }
  return { total: latest.size, active, attention, versions: records.length };
}

function statusTone(status: CapabilityStatus): string {
  if (status === 'active' || status === 'tested') return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200';
  if (status === 'unverified' || status === 'approval_required') return 'border-amber-500/25 bg-amber-500/10 text-amber-200';
  if (status === 'disabled' || status === 'retired') return 'border-rose-500/25 bg-rose-500/10 text-rose-200';
  return 'border-border/40 bg-white/5 text-muted-foreground';
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

function latestByCapability(records: CapabilityRecord[]): CapabilityRecord[] {
  const latest = new Map<string, CapabilityRecord>();
  for (const record of records) {
    if (!latest.has(record.capabilityId)) latest.set(record.capabilityId, record);
  }
  return [...latest.values()];
}

export function GeneratedCapabilitiesSection() {
  const t = useT();
  const [records, setRecords] = useState<CapabilityRecord[] | null>(null);
  const [builtins, setBuiltins] = useState<BuiltinCapability[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [result, builtinResult] = await Promise.all([
        listCapabilities(),
        listBuiltins().catch(() => null),
      ]);
      setRecords(result.capabilities);
      setBuiltins(builtinResult?.builtins ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(() => latestByCapability(records ?? []), [records]);
  const counts = useMemo(() => summarizeCapabilities(records ?? []), [records]);
  const versionsByCapability = useMemo(() => {
    const map = new Map<string, CapabilityRecord[]>();
    for (const record of records ?? []) {
      const list = map.get(record.capabilityId) ?? [];
      list.push(record);
      map.set(record.capabilityId, list);
    }
    return map;
  }, [records]);

  const run = useCallback(async (id: string, action: () => Promise<unknown>) => {
    setBusy(id);
    setActionError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'unavailable');
    } finally {
      setBusy(null);
    }
  }, [load]);

  const rebuild = useCallback((record: CapabilityRecord) => {
    useCommandStore.getState().dispatch({
      tab: 'chat',
      params: {
        prompt: t('studio.generated.rebuildPrompt', {
          id: record.capabilityId,
          version: record.version,
        }),
      },
    });
  }, [t]);

  if (loading && records === null) {
    return <p className="text-xs text-muted-foreground">{t('studio.loading')}</p>;
  }
  if (error || records === null) {
    return (
      <div className="glass-card-subtle rounded-xl border border-rose-500/20 px-3 py-2.5 text-xs text-rose-200">
        <p>{t('studio.loadFailed', { what: t('studio.section.generated').toLowerCase(), reason: error ?? 'unavailable' })}</p>
        <button type="button" onClick={() => void load()} className="glass-button mt-2 rounded-lg px-3 py-1 text-[11px] text-foreground">
          {t('studio.retry')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-muted-foreground">{t('studio.generated.hint')}</p>
      <GapsSection />
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <StatCard label={t('studio.generated.total')} value={counts.total} />
        <StatCard label={t('studio.generated.active')} value={counts.active} />
        <StatCard label={t('studio.generated.attention')} value={counts.attention} tone="attention" />
        <StatCard label={t('studio.generated.versions')} value={counts.versions} />
      </div>

      {actionError ? (
        <p className="text-[11px] text-rose-300">{t('studio.generated.actionFailed', { reason: actionError })}</p>
      ) : null}

      <div className="glass-card rounded-xl p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            <Sparkles size={12} /> {t('studio.section.generated')}
          </h2>
          <button type="button" onClick={() => void load()} aria-label={t('studio.retry')} className="rounded-md p-1 text-muted-foreground hover:text-foreground">
            <RefreshCw size={12} />
          </button>
        </div>

        {rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('studio.generated.empty')}</p>
        ) : (
          <ul className="space-y-2">
            {rows.map((record) => {
              const versions = versionsByCapability.get(record.capabilityId) ?? [];
              const usage = record.usage;
              const testKey = record.testStatus ? TEST_KEY[record.testStatus] : undefined;
              const manifest = record.manifest && typeof record.manifest === 'object'
                ? record.manifest as Record<string, unknown>
                : {};
              const inputCount = Array.isArray(manifest.inputs) ? manifest.inputs.length : 0;
              const outputCount = Array.isArray(manifest.outputs) ? manifest.outputs.length : 0;
              return (
                <li key={record.capabilityId} className="rounded-xl border border-border/20 bg-white/[0.02] px-3 py-2">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="truncate text-xs font-medium text-foreground">{record.title || record.capabilityId}</span>
                        <span className={cn('rounded-full border px-1.5 py-px text-[9px] uppercase tracking-wide', statusTone(record.status))}>
                          {t(STATUS_KEY[record.status])}
                        </span>
                        <span className="font-mono text-[10px] text-muted-foreground">v{record.version}</span>
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9.5px] text-muted-foreground/80">
                        <span className="font-mono">{record.capabilityId}</span>
                        <span>{record.kind}</span>
                        <span>{t(`studio.generated.scope.${record.scope}` as TranslationKey)}</span>
                        {testKey ? <span className={record.testStatus === 'verified' ? 'text-emerald-300/90' : 'text-amber-300/90'}>{t(testKey)}</span> : null}
                        <span>{usage && usage.total > 0 ? t('studio.generated.usage', { ok: usage.ok, failed: usage.failed }) : t('studio.generated.noUsage')}</span>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      {record.scope === 'workspace' && record.testStatus === 'verified' && record.status !== 'retired' ? (
                        <button
                          type="button"
                          disabled={busy === record.capabilityId}
                          title={t('studio.generated.promoteHint')}
                          onClick={() => void run(record.capabilityId, () => promoteCapability(record.capabilityId, record.version))}
                          className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground disabled:opacity-50"
                        >
                          {t('studio.generated.promote')}
                        </button>
                      ) : null}
                      {record.testStatus !== 'verified' || record.status === 'disabled' ? (
                        <button
                          type="button"
                          onClick={() => rebuild(record)}
                          className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground"
                        >
                          {t('studio.generated.rebuild')}
                        </button>
                      ) : null}
                      {record.status === 'active' ? (
                        <button
                          type="button"
                          disabled={busy === record.capabilityId}
                          onClick={() => void run(record.capabilityId, () => deactivateCapability(record.capabilityId, record.version))}
                          className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground disabled:opacity-50"
                        >
                          {t('studio.generated.deactivate')}
                        </button>
                      ) : ACTIONABLE.has(record.status) ? (
                        <button
                          type="button"
                          disabled={busy === record.capabilityId}
                          onClick={() => void run(record.capabilityId, () => activateCapability(record.capabilityId, record.version))}
                          className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground disabled:opacity-50"
                        >
                          {t('studio.generated.activate')}
                        </button>
                      ) : null}
                      {versions.length > 1 ? (
                        <button
                          type="button"
                          disabled={busy === record.capabilityId}
                          onClick={() => void run(record.capabilityId, () => rollbackCapability(record.capabilityId))}
                          className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground disabled:opacity-50"
                        >
                          {t('studio.generated.rollback')}
                        </button>
                      ) : null}
                      {record.status !== 'retired' ? (
                        <button
                          type="button"
                          disabled={busy === record.capabilityId}
                          onClick={() => {
                            if (typeof window !== 'undefined' && !window.confirm(t('studio.generated.confirmRemove', { id: record.capabilityId }))) return;
                            void run(record.capabilityId, () => removeCapability(record.capabilityId));
                          }}
                          className="rounded-lg border border-rose-500/25 bg-rose-500/10 px-2.5 py-1 text-[10px] text-rose-200 disabled:opacity-50"
                        >
                          {t('studio.generated.remove')}
                        </button>
                      ) : null}
                    </div>
                  </div>

                  <details className="mt-1.5 text-[10px] text-muted-foreground">
                    <summary className="cursor-pointer select-none text-[10px] text-muted-foreground/80">
                      {inputCount > 0 || outputCount > 0
                        ? `${inputCount} input(s) Â· ${outputCount} output(s)`
                        : record.dir}
                    </summary>
                    <div className="mt-1 space-y-0.5 font-mono text-[9px] text-muted-foreground/70">
                      {record.dir ? <p className="break-all">{record.dir}</p> : null}
                      {record.sourceDigest ? <p>source: {record.sourceDigest.slice(0, 16)}â€¦</p> : null}
                      {record.testDigest ? <p>test: {record.testDigest.slice(0, 16)}â€¦</p> : null}
                      {versions.length > 1 ? (
                        <p>versions: {versions.map((item) => `${item.version} (${item.status})`).join(', ')}</p>
                      ) : null}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {builtins.length > 0 ? (
        <div className="glass-card rounded-xl p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <Sparkles size={12} /> {t('studio.generated.builtins')}
            </h2>
            <span className="font-mono text-[10px] text-muted-foreground/70">{builtins.length}</span>
          </div>
          <p className="mb-2 text-[11px] text-muted-foreground">{t('studio.generated.builtinHint')}</p>
          <ul className="space-y-2">
            {builtins.map((item) => (
              <li key={item.id} className="rounded-xl border border-border/20 bg-white/[0.02] px-3 py-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="truncate text-xs font-medium text-foreground">{item.title}</span>
                  <span className="rounded-full border border-sky-500/25 bg-sky-500/10 px-1.5 py-px text-[9px] uppercase tracking-wide text-sky-200">
                    {t('studio.generated.builtinBadge')}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">{item.name}</span>
                </div>
                <p className="mt-0.5 text-[10px] text-muted-foreground/80">{item.description}</p>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9.5px] text-muted-foreground/70">
                  <span>{t('studio.generated.builtinInputs', { count: item.inputs.length })}</span>
                  {item.inputs.slice(0, 4).map((input) => (
                    <span key={input.name} className="font-mono">{input.name}</span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
