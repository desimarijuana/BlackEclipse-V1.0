'use client';

// ── Agent Workspace — Context panel ───────────────────────────────────────────
// Answers one question the other tabs do not: how much of the model's context
// window this run has used, and what fills it. The numbers are read from the
// live workspace store (already fed by the chat SSE stream) plus the declared
// model catalog for the window. Honesty rule (docs/agent-workspace.md): an
// unreported value renders "Not available" — the gauge is never faked full.

import { useT } from '@/lib/i18n';
import { useModelCatalog } from '@/lib/agent/model-catalog';
import { cn } from '@/lib/utils';
import { formatCost, formatCount, formatTokens } from '@/lib/agent-workspace/format';
import {
  buildBreakdown,
  resolveContextWindow,
  sourceColor,
  usagePercent,
} from '@/lib/agent-workspace/context-usage';
import type { ContextSource, ContextUsage, ModelInfo, RunTelemetry } from '@/lib/agent-workspace/types';
import { Section, StatTile } from './ui';

export function ContextPanel({
  context,
  sources,
  telemetry,
  model,
}: {
  context: ContextUsage;
  sources: ContextSource[];
  telemetry: RunTelemetry;
  model: ModelInfo;
}) {
  const t = useT();
  const catalog = useModelCatalog();
  const notAvailable = t('workspace.notAvailable');

  // The runtime-reported window wins when known; otherwise resolve it from the
  // declared catalog. Null means genuinely unknown → "Not available", no gauge.
  const window =
    context.windowKnown && context.windowTokens != null
      ? context.windowTokens
      : resolveContextWindow(catalog, model.provider, model.model);

  const used = telemetry.totalTokens;
  const percent = usagePercent(used, window, window != null);
  const remaining = percent != null && window != null && used != null ? Math.max(0, window - used) : null;
  const segments = buildBreakdown(sources, window);

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <div className="flex items-baseline justify-between px-0.5">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/70">
            {t('workspace.usage')}
          </span>
          <span className="text-[12px] tabular-nums text-foreground/85">
            {percent != null ? `${percent.toFixed(0)}%` : notAvailable}
          </span>
        </div>

        <div
          role="img"
          aria-label={`${t('workspace.usage')}: ${percent != null ? `${percent.toFixed(0)}%` : notAvailable}`}
          className="flex h-2 w-full overflow-hidden rounded-full bg-white/[0.06]"
        >
          {segments.length > 0 ? (
            segments.map((s) => (
              <div
                key={s.id}
                className={cn('h-full', s.color)}
                style={{ width: `${s.percent}%` }}
                title={`${s.label} · ${formatTokens(s.tokens)}`}
              />
            ))
          ) : percent != null ? (
            <div className="h-full bg-primary/70" style={{ width: `${percent}%` }} />
          ) : null}
        </div>

        {segments.length > 0 && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 px-0.5 pt-1">
            {segments.map((s) => (
              <span key={s.id} className="flex items-center gap-1 text-[10.5px] text-muted-foreground/70">
                <span className={cn('h-1.5 w-1.5 rounded-full', s.color)} />
                <span className="capitalize">{s.label}</span>
                <span className="tabular-nums text-muted-foreground/50">{formatTokens(s.tokens)}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <StatTile label={t('workspace.contextWindow')} unavailable={notAvailable} value={window != null ? formatCount(window) : ''} />
        <StatTile label={t('workspace.totalTokens')} unavailable={notAvailable} value={formatTokens(used)} />
        <StatTile label={t('workspace.inputTokens')} unavailable={notAvailable} value={formatTokens(telemetry.promptTokens)} />
        <StatTile label={t('workspace.outputTokens')} unavailable={notAvailable} value={formatTokens(telemetry.completionTokens)} />
        <StatTile label={t('workspace.remaining')} unavailable={notAvailable} value={remaining != null ? formatTokens(remaining) : ''} />
        <StatTile label={t('workspace.modelSteps')} unavailable={notAvailable} value={telemetry.modelSteps != null ? String(telemetry.modelSteps) : ''} />
        <StatTile label={t('workspace.model')} unavailable={notAvailable} value={model.model ?? ''} />
        <StatTile label={t('workspace.provider')} unavailable={notAvailable} value={model.provider ?? ''} />
        <StatTile label={t('workspace.turnsKept')} unavailable={notAvailable} value={context.turnsKept != null ? String(context.turnsKept) : ''} />
        <StatTile label={t('workspace.turnsDropped')} unavailable={notAvailable} value={context.turnsDropped != null ? String(context.turnsDropped) : ''} />
        <StatTile label={t('workspace.memoriesUsed')} unavailable={notAvailable} value={context.memoriesUsed != null ? String(context.memoriesUsed) : ''} />
        <StatTile label={t('workspace.estCost')} unavailable={notAvailable} value={formatCost(telemetry.costUsd, telemetry.costKnown)} />
      </div>

      <Section
        title={t('workspace.contextSources')}
        count={sources.length}
        empty={sources.length === 0}
        emptyText={t('workspace.empty')}
      >
        <ul className="space-y-0.5">
          {sources.map((s, i) => (
            <li key={s.id} className="flex items-center gap-2 px-1 py-1 text-[11.5px]">
              <span className={cn('h-2 w-2 shrink-0 rounded-full', sourceColor(i))} />
              <span className="min-w-0 flex-1 truncate capitalize text-foreground/80">{s.source ?? s.id}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground/60">
                {s.tokens != null ? formatTokens(s.tokens) : notAvailable}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
