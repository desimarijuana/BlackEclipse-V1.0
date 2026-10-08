'use client';

// ── Agent Workspace — Context panel ────────────────────────────────────────────
// What the run is currently using: the named prompt segments the runtime
// resolved (`prompt.plan`) plus live counts. Every value comes from the runtime;
// anything unreported renders "Not available" rather than a guess.

import { useT } from '@/lib/i18n';
import type { ContextSource, ContextUsage } from '@/lib/agent-workspace/types';
import { formatCount, formatTokens } from '@/lib/agent-workspace/format';
import { Section, StatTile } from './ui';

export function ContextPanel({ context, sources }: { context: ContextUsage; sources: ContextSource[] }) {
  const t = useT();
  // Percent of the window used, only when the runtime reported both numbers.
  const windowPct =
    context.windowKnown && context.windowTokens && context.windowTokens > 0 && context.droppedTokensEstimate != null
      ? Math.min(100, Math.round((context.droppedTokensEstimate / context.windowTokens) * 100))
      : null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <StatTile
          label={t('workspace.filesInspected')}
          value={context.filesInspected > 0 ? formatCount(context.filesInspected) : undefined}
          unavailable={t('workspace.notAvailable')}
        />
        <StatTile
          label={t('workspace.toolsUsed')}
          value={context.toolsUsed > 0 ? formatCount(context.toolsUsed) : undefined}
          unavailable={t('workspace.notAvailable')}
        />
        <StatTile
          label={t('workspace.linesInspected')}
          value={context.linesInspected > 0 ? formatCount(context.linesInspected) : undefined}
          unavailable={t('workspace.notAvailable')}
        />
        <StatTile
          label={t('workspace.researchSources')}
          value={context.researchSources > 0 ? formatCount(context.researchSources) : undefined}
          unavailable={t('workspace.notAvailable')}
        />
        <StatTile
          label={t('workspace.memoriesUsed')}
          value={context.memoriesUsed != null ? formatCount(context.memoriesUsed) : undefined}
          unavailable={t('workspace.notAvailable')}
        />
        <StatTile
          label={t('workspace.panel.artifacts')}
          value={context.artifacts > 0 ? formatCount(context.artifacts) : undefined}
          unavailable={t('workspace.notAvailable')}
        />
      </div>

      <div className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2">
        <div className="flex items-center justify-between text-[11px] text-muted-foreground/70">
          <span>{t('workspace.contextWindow')}</span>
          {context.windowKnown && context.windowTokens != null ? (
            <span className="font-mono tabular-nums">
              {windowPct != null ? `${windowPct}% · ` : ''}
              {formatTokens(context.windowTokens)}
            </span>
          ) : (
            <span className="text-muted-foreground/50">{t('workspace.notAvailable')}</span>
          )}
        </div>
        {context.turnsKept != null && (
          <p className="mt-1 text-[11px] text-muted-foreground/60 tabular-nums">
            {context.turnsKept} {t('workspace.panel.tasks').toLowerCase()} · {context.turnsDropped ?? 0} trimmed
          </p>
        )}
      </div>

      <Section title={t('workspace.contextSources')} count={sources.length} empty={sources.length === 0} emptyText={t('workspace.notAvailable')}>
        <ul className="space-y-0.5">
          {sources.map((source) => (
            <li key={source.id} className="flex items-center gap-2 rounded-lg px-2 py-1 text-[12px]">
              <span className="min-w-0 flex-1 truncate text-foreground/80" title={source.id}>
                {source.source ?? source.id}
              </span>
              {source.tokens != null && (
                <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/60">{formatTokens(source.tokens)}</span>
              )}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
