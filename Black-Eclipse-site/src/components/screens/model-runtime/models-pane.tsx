'use client';

// ── Models pane ──────────────────────────────────────────────────────────────
// The normalized model registry: capabilities as STATES (supported / degraded /
// unsupported / unknown), context window, pricing and status. Unknown pricing
// and unknown capabilities are shown honestly, never guessed.

import { useMemo, useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import type { TranslateFn } from '@/lib/i18n/translate';
import type { CapabilityState, RuntimeModelView, RuntimeProviderView } from '@/lib/harness/clients/model-runtime-browser';
import { dynKey, pricingKey } from '@/lib/harness/clients/model-runtime-browser';
import { EmptyState } from './providers-pane';

interface Props {
  providers: RuntimeProviderView[];
  models: RuntimeModelView[];
}

const CAPABILITY_ORDER = [
  'text', 'reasoning', 'tool_calling', 'structured_output', 'vision',
  'long_context', 'streaming', 'parallel_tool_calls', 'embeddings',
  'image_generation', 'audio_input', 'audio_output', 'computer_use', 'code_execution',
];

export function ModelsPane({ providers, models }: Props) {
  const t = useT();
  const [providerFilter, setProviderFilter] = useState<string>('');
  const filtered = useMemo(
    () => (providerFilter ? models.filter((m) => m.providerId === providerFilter) : models),
    [models, providerFilter],
  );

  if (models.length === 0) {
    return <EmptyState text={t('modelRuntime.models.empty')} />;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {t('modelRuntime.col.provider')}
        </label>
        <select
          value={providerFilter}
          onChange={(e) => setProviderFilter(e.target.value)}
          className="glass-card-subtle rounded-lg px-2 py-1 text-[12px] text-foreground outline-none"
        >
          <option value="">{t('modelRuntime.models.allProviders')}</option>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
        <span className="text-[11px] text-muted-foreground">
          {t('modelRuntime.models.count', { count: filtered.length })}
        </span>
      </div>

      <div className="glass-card overflow-x-auto rounded-2xl p-1">
        <table className="w-full min-w-[720px] border-collapse text-[12px] text-foreground">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.model')}</th>
              <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.context')}</th>
              <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.pricing')}</th>
              <th className="px-3 py-2 font-semibold">{t('modelRuntime.col.capabilities')}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((m) => (
              <tr key={m.qualifiedId} className="align-top odd:bg-white/[0.02]">
                <td className="px-3 py-2">
                  <div className="font-medium">{m.displayName}</div>
                  <div className="text-[10px] text-muted-foreground">{m.qualifiedId}</div>
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {m.contextWindow ? formatTokens(m.contextWindow) : t('modelRuntime.unknown')}
                </td>
                <td className="px-3 py-2 text-muted-foreground">{pricingSentence(m, t)}</td>
                <td className="px-3 py-2">
                  <CapabilityChips states={m.capabilities.states} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CapabilityChips({ states }: { states: Record<string, CapabilityState> }) {
  const t = useT();
  const shown = CAPABILITY_ORDER.filter((key) => states[key] === 'supported' || states[key] === 'degraded');
  if (shown.length === 0) {
    return <span className="text-muted-foreground">{t('modelRuntime.capabilities.none')}</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((key) => (
        <span
          key={key}
          className={
            'rounded-md px-1.5 py-0.5 text-[10px] ' +
            (states[key] === 'supported'
              ? 'bg-emerald-500/10 text-emerald-300'
              : 'bg-amber-500/10 text-amber-300')
          }
        >
          {t(`modelRuntime.capability.name.${key}` as never)}
        </span>
      ))}
    </div>
  );
}

function pricingSentence(m: RuntimeModelView, t: TranslateFn): string {
  const p = m.pricing;
  if (p.kind === 'free') return t('modelRuntime.pricing.free');
  if (p.kind === 'unknown') return t('modelRuntime.pricing.unknown');
  if (p.kind === 'per_request' && p.perRequest !== null) {
    return t('modelRuntime.pricing.perRequest', { amount: `$${p.perRequest}` });
  }
  if (p.kind === 'per_token' && p.inputPerMillion !== null) {
    const out = p.outputPerMillion !== null ? `$${p.outputPerMillion}` : t('modelRuntime.unknown');
    return t('modelRuntime.pricing.perToken', { input: `$${p.inputPerMillion}`, output: out });
  }
  return dynKey(t, pricingKey(p.kind));
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}
