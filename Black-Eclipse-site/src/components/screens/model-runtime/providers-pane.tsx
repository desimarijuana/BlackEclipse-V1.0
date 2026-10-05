'use client';

// ── Providers pane ───────────────────────────────────────────────────────────
// Provider list with health/enabled state. The runtime owns configuration; this
// pane is read-only and shows an honest "not measured yet" state when a provider
// has no traffic. Credentials are configured in Settings › AI, never here.

import { useT } from '@/lib/i18n/use-t';
import { CheckCircle2, CircleSlash, MinusCircle } from '@/lib/icons';
import type { RuntimeModelView, RuntimeProviderView } from '@/lib/harness/model-runtime-browser';
import { healthBucket, dynKey, type HealthRow } from '@/lib/harness/model-runtime-browser';

interface Props {
  providers: RuntimeProviderView[];
  models: RuntimeModelView[];
  health: HealthRow[];
}

export function ProvidersPane({ providers, models, health }: Props) {
  const t = useT();
  const healthById = new Map(health.map((h) => [String(h.id), h]));
  if (providers.length === 0) {
    return <EmptyState text={t('modelRuntime.providers.empty')} />;
  }
  return (
    <div className="glass-card rounded-2xl p-1">
      <div className="grid grid-cols-[1.4fr_1fr_0.6fr_0.9fr_0.9fr] gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span>{t('modelRuntime.col.provider')}</span>
        <span>{t('modelRuntime.col.kind')}</span>
        <span>{t('modelRuntime.col.models')}</span>
        <span>{t('modelRuntime.col.status')}</span>
        <span>{t('modelRuntime.col.health')}</span>
      </div>
      {providers.map((p) => {
        const modelCount = models.filter((m) => m.providerId === p.id).length;
        const row = healthById.get(p.id);
        const ratio = typeof row?.health === 'number' ? row.health : null;
        const bucket = healthBucket(ratio);
        return (
          <div
            key={p.id}
            className="grid grid-cols-[1.4fr_1fr_0.6fr_0.9fr_0.9fr] items-center gap-2 rounded-xl px-3 py-2 text-[12px] text-foreground odd:bg-white/[0.02]"
          >
            <span className="flex items-center gap-2 truncate">
              <Dot enabled={p.enabled} />
              <span className="truncate font-medium">{p.label}</span>
              <span className="truncate text-[10px] text-muted-foreground">{p.id}</span>
            </span>
            <span className="truncate text-muted-foreground">
              {p.openaiCompatible ? t('modelRuntime.kind.openaiCompatible') : p.kind}
            </span>
            <span className="text-muted-foreground">{modelCount}</span>
            <span className="text-muted-foreground">
              {p.enabled ? t('modelRuntime.enabled') : t('modelRuntime.disabled')}
              {p.keyless ? ` · ${t('modelRuntime.keyless')}` : ''}
            </span>
            <HealthPill bucket={bucket} ratio={ratio} circuit={typeof row?.circuit === 'string' ? row.circuit : null} />
          </div>
        );
      })}
    </div>
  );
}

function Dot({ enabled }: { enabled: boolean }) {
  return enabled ? (
    <CheckCircle2 size={13} className="shrink-0 text-emerald-400" />
  ) : (
    <CircleSlash size={13} className="shrink-0 text-muted-foreground/60" />
  );
}

function HealthPill({
  bucket,
  ratio,
  circuit,
}: {
  bucket: 'good' | 'watch' | 'bad' | 'unknown';
  ratio: number | null;
  circuit: string | null;
}) {
  const t = useT();
  const color =
    bucket === 'good'
      ? 'text-emerald-300'
      : bucket === 'watch'
        ? 'text-amber-300'
        : bucket === 'bad'
          ? 'text-rose-300'
          : 'text-muted-foreground';
  const label =
    ratio === null ? t('modelRuntime.health.unknown') : `${Math.round(ratio * 100)}%`;
  return (
    <span className={`flex items-center gap-1.5 ${color}`}>
      {label}
      {circuit && circuit !== 'healthy' && (
        <span className="text-[10px] text-muted-foreground">· {dynKey(t, `modelRuntime.circuit.${circuit}`)}</span>
      )}
    </span>
  );
}

export function EmptyState({ text }: { text: string }) {
  return (
    <div className="glass-card-subtle flex items-center gap-2 rounded-xl p-4 text-[12px] text-muted-foreground">
      <MinusCircle size={14} />
      {text}
    </div>
  );
}
