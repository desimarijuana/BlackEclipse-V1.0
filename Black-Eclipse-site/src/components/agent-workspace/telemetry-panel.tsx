'use client';

// ── Agent Workspace — Telemetry & Model panel ─────────────────────────────────
// Run telemetry (duration, tokens, tool calls, retries, errors) and the resolved
// model/provider. Cost is shown only when the runtime reports it — never derived
// from a price table the UI does not own.

import { useT } from '@/lib/i18n';
import type { ModelInfo, RunTelemetry } from '@/lib/agent-workspace/types';
import { formatCost, formatCount, formatElapsed } from '@/lib/agent-workspace/format';
import { Section, StatTile } from './ui';

export function TelemetryPanel({
  telemetry,
  model,
  nowMs,
}: {
  telemetry: RunTelemetry;
  model: ModelInfo;
  nowMs: number;
}) {
  const t = useT();
  const elapsed =
    telemetry.startedAt != null
      ? formatElapsed(telemetry.startedAt, telemetry.finishedAt ?? nowMs)
      : undefined;
  const cost = formatCost(telemetry.costUsd, telemetry.costKnown);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <StatTile label={t('workspace.duration')} value={elapsed} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.modelSteps')} value={telemetry.modelSteps != null ? formatCount(telemetry.modelSteps) : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.inputTokens')} value={telemetry.promptTokens != null ? formatCount(telemetry.promptTokens) : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.outputTokens')} value={telemetry.completionTokens != null ? formatCount(telemetry.completionTokens) : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.toolCalls')} value={telemetry.toolCalls > 0 ? formatCount(telemetry.toolCalls) : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.toolErrors')} value={telemetry.toolErrors > 0 ? formatCount(telemetry.toolErrors) : undefined} unavailable={t('workspace.notAvailable')} tone={telemetry.toolErrors > 0 ? 'failed' : 'default'} />
        <StatTile label={t('workspace.retries')} value={telemetry.retries > 0 ? formatCount(telemetry.retries) : undefined} unavailable={t('workspace.notAvailable')} tone={telemetry.retries > 0 ? 'running' : 'default'} />
        <StatTile label={t('workspace.estCost')} value={cost || undefined} unavailable={t('workspace.notAvailable')} />
      </div>

      <Section title={t('workspace.model')} empty={!model.provider && !model.model} emptyText={t('workspace.notAvailable')}>
        <div className="space-y-0.5">
          <Row label={t('workspace.provider')} value={model.provider} />
          <Row label={t('workspace.model')} value={model.model} />
          <Row label={t('workspace.tokens')} value={telemetry.totalTokens != null ? formatCount(telemetry.totalTokens) : undefined} />
        </div>
      </Section>
    </div>
  );
}

function Row({ label, value }: { label: string; value?: string }) {
  const t = useT();
  return (
    <div className="flex items-center gap-2 rounded-lg px-2 py-1 text-[12px]">
      <span className="min-w-0 flex-1 text-muted-foreground/70">{label}</span>
      <span className="shrink-0 truncate font-mono text-[11px] text-foreground/80" title={value}>
        {value ?? t('workspace.notAvailable')}
      </span>
    </div>
  );
}
