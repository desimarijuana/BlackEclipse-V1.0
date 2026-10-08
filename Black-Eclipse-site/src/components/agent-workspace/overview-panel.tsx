'use client';

// ── Agent Workspace — Overview panel ────────────────────────────────────────────
// The "what is happening right now" summary: agent state, current task/tool,
// iteration, elapsed time, tokens, cost — plus the plan and an at-a-glance count
// strip. Every value is runtime-derived; missing values read "Not available".

import { useT } from '@/lib/i18n';
import type { AgentWorkspaceState } from '@/lib/agent-workspace/types';
import { formatCost, formatElapsed, formatTokens } from '@/lib/agent-workspace/format';
import { Section, StatTile, statusIcon, statusTone } from './ui';
import { TasksPanel } from './tasks-panel';

const STATUS_KEY = {
  idle: 'workspace.status.idle',
  planning: 'workspace.status.planning',
  running: 'workspace.status.running',
  waiting: 'workspace.status.waiting',
  paused: 'workspace.status.paused',
  completed: 'workspace.status.completed',
  failed: 'workspace.status.failed',
  cancelled: 'workspace.status.cancelled',
} as const;

export function OverviewPanel({ state, nowMs }: { state: AgentWorkspaceState; nowMs: number }) {
  const t = useT();
  const { execution, telemetry, model, tasks } = state;
  const runningTask = tasks.find((x) => x.status === 'running') ?? tasks.find((x) => x.status === 'pending');
  const elapsed = execution.startedAt != null ? formatElapsed(execution.startedAt, telemetry.finishedAt ?? nowMs) : undefined;
  const cost = formatCost(telemetry.costUsd, telemetry.costKnown);
  const tone = statusTone(execution.status);

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className={tone === 'running' ? 'text-primary' : tone === 'failed' ? 'text-rose-400' : tone === 'ok' ? 'text-emerald-400' : 'text-muted-foreground/60'}>
            {statusIcon(execution.status, 15)}
          </span>
          <span className="text-[13px] font-medium text-foreground">{t('workspace.agent')}</span>
          <span className="ml-auto text-[12px] font-medium text-foreground/80">{t(STATUS_KEY[execution.status])}</span>
        </div>
        {(runningTask || execution.currentTool) && (
          <div className="mt-2 space-y-1 border-t border-white/8 pt-2 text-[11.5px]">
            {runningTask && (
              <div className="flex gap-2">
                <span className="shrink-0 text-muted-foreground/60">{t('workspace.currentTask')}</span>
                <span className="min-w-0 flex-1 truncate text-foreground/85">{runningTask.title}</span>
              </div>
            )}
            {execution.currentTool && (
              <div className="flex gap-2">
                <span className="shrink-0 text-muted-foreground/60">{t('workspace.currentTool')}</span>
                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-foreground/85">{execution.currentTool}</span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <StatTile label={t('workspace.elapsed')} value={elapsed} unavailable={t('workspace.notAvailable')} tone={tone === 'running' ? 'running' : 'default'} />
        <StatTile
          label={t('workspace.iteration')}
          value={execution.iteration != null ? (execution.maxIterations != null ? `${execution.iteration} / ${execution.maxIterations}` : String(execution.iteration)) : undefined}
          unavailable={t('workspace.notAvailable')}
        />
        <StatTile label={t('workspace.tokens')} value={telemetry.totalTokens != null ? formatTokens(telemetry.totalTokens) : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.cost')} value={cost || undefined} unavailable={t('workspace.notAvailable')} />
      </div>

      {model.provider || model.model ? (
        <div className="flex flex-wrap gap-x-3 gap-y-1 px-0.5 text-[11px] text-muted-foreground/60">
          {model.provider && <span>{model.provider}</span>}
          {model.model && <span className="font-mono text-foreground/70">{model.model}</span>}
        </div>
      ) : null}

      <Section title={t('workspace.panel.tasks')} count={tasks.length} empty={tasks.length === 0} emptyText={t('workspace.empty')}>
        <TasksPanel tasks={tasks} />
      </Section>
    </div>
  );
}
