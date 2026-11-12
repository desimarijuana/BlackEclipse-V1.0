'use client';

// ── Health pane ──────────────────────────────────────────────────────────────
// Provider/model health: availability, latency percentiles, error rate, circuit
// state and tool/structured-output success. Absent metrics render honestly as
// "not measured yet" — never a fabricated 0.

import { useT } from '@/lib/i18n/use-t';
import type { RuntimeHealthView, RuntimeProviderView } from '@/lib/harness/clients/model-runtime-browser';
import { healthBucket } from '@/lib/harness/clients/model-runtime-browser';
import { dynKey } from '@/lib/harness/clients/model-runtime-browser';
import { EmptyState } from './providers-pane';

interface Props {
  health: RuntimeHealthView | null;
  providers: RuntimeProviderView[];
}

export function HealthPane({ health, providers }: Props) {
  const t = useT();
  if (!health) return <EmptyState text={t('modelRuntime.health.empty')} />;
  const order = new Map(providers.map((p, i) => [p.id, i]));
  const rows = [...health.providers].sort(
    (a, b) => (order.get(String(a.id)) ?? 999) - (order.get(String(b.id)) ?? 999),
  );

  return (
    <div className="glass-card overflow-x-auto rounded-2xl p-1">
      <table className="w-full min-w-[720px] border-collapse text-[12px] text-foreground">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.provider')}</th>
            <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.availability')}</th>
            <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.errorRate')}</th>
            <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.latencyP50')}</th>
            <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.latencyP95')}</th>
            <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.circuit')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const ratio = typeof row.health === 'number' ? row.health : null;
            const bucket = healthBucket(ratio);
            const color =
              bucket === 'good'
                ? 'text-emerald-300'
                : bucket === 'watch'
                  ? 'text-amber-300'
                  : bucket === 'bad'
                    ? 'text-rose-300'
                    : 'text-muted-foreground';
            return (
              <tr key={String(row.id)} className="odd:bg-white/[0.02]">
                <td className="px-3 py-2 font-medium">{String(row.label ?? row.id)}</td>
                <td className={`px-3 py-2 ${color}`}>
                  {ratio === null ? t('modelRuntime.health.notMeasured') : `${Math.round(ratio * 100)}%`}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {typeof row.errorRate === 'number' ? `${Math.round(row.errorRate * 100)}%` : t('modelRuntime.unknown')}
                </td>
                <td className="px-3 py-2 text-muted-foreground">{ms(row.latency?.p50)}</td>
                <td className="px-3 py-2 text-muted-foreground">{ms(row.latency?.p95)}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  {row.circuit
                    ? dynKey(t, `modelRuntime.circuit.${String(row.circuit)}`)
                    : t('modelRuntime.circuit.healthy')}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ms(value: number | null | undefined): string {
  return typeof value === 'number' ? `${Math.round(value)} ms` : '—';
}
