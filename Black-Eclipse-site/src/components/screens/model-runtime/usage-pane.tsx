'use client';

// ── Usage pane ───────────────────────────────────────────────────────────────
// Requests, tokens, estimated cost and latency from the Model Runtime's own
// store. Unknown cost is reported as unknown, never $0. Persisted per-request
// rows are shown below the summary.

import { useT } from '@/lib/i18n/use-t';
import type { RuntimeUsageView } from '@/lib/harness/model-runtime-browser';
import { EmptyState } from './providers-pane';

export function UsagePane({ usage }: { usage: RuntimeUsageView | null }) {
  const t = useT();
  if (!usage) return <EmptyState text={t('modelRuntime.usage.empty')} />;

  const cards: Array<{ label: string; value: string }> = [
    { label: t('modelRuntime.usage.requests'), value: String(usage.requests) },
    { label: t('modelRuntime.usage.successful'), value: String(usage.successful) },
    { label: t('modelRuntime.usage.failed'), value: String(usage.failed) },
    { label: t('modelRuntime.usage.inputTokens'), value: formatNumber(usage.inputTokens) },
    { label: t('modelRuntime.usage.outputTokens'), value: formatNumber(usage.outputTokens) },
    { label: t('modelRuntime.usage.totalTokens'), value: formatNumber(usage.totalTokens) },
    {
      label: t('modelRuntime.usage.cost'),
      value: usage.estimatedCost > 0 ? `$${usage.estimatedCost.toFixed(4)}` : t('modelRuntime.usage.costUnknown'),
    },
    {
      label: t('modelRuntime.usage.avgLatency'),
      value: usage.averageLatencyMs === null ? t('modelRuntime.unknown') : `${Math.round(usage.averageLatencyMs)} ms`,
    },
  ];

  const recent = usage.persisted?.recentRequests ?? [];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className="glass-card-subtle rounded-xl p-3">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{c.label}</div>
            <div className="mt-0.5 text-[15px] font-semibold text-foreground">{c.value}</div>
          </div>
        ))}
      </div>

      {recent.length > 0 && (
        <section className="glass-card overflow-x-auto rounded-2xl p-1">
          <table className="w-full min-w-[640px] border-collapse text-[12px] text-foreground">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.model')}</th>
                <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.task')}</th>
                <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.tokens')}</th>
                <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.latency')}</th>
                <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.status')}</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={String(r.requestId)} className="odd:bg-white/[0.02]">
                  <td className="px-3 py-1.5">
                    <span className="text-muted-foreground">{String(r.provider)}</span>/{String(r.model)}
                  </td>
                  <td className="px-3 py-1.5 text-muted-foreground">{r.task ? String(r.task) : '—'}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{formatNumber(Number(r.totalTokens) || 0)}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">
                    {r.latencyMs ? `${Math.round(Number(r.latencyMs))} ms` : '—'}
                  </td>
                  <td className="px-3 py-1.5">
                    <span className={r.success ? 'text-emerald-300' : 'text-rose-300'}>
                      {r.success ? t('modelRuntime.ok') : t('modelRuntime.failed')}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}
