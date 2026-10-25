'use client';

// ── ParallelAgentsPanel — the live fan-out card ─────────────────────────────
// One row per delegated part: which agent is on it, what it is doing right now,
// how far it is (the RUNTIME's step counter), and what it has really cost so
// far. Sits above the activity feed so a fan-out reads as parallel work instead
// of a single stream of tools.
//
// Honesty rules:
//  - progress is `step / maxSteps` from the runtime; with no known ceiling the
//    bar is indeterminate and no percentage is printed;
//  - cost is the declared price of the real tokens; an unpriced model shows "—",
//    never "$0.00";
//  - a failed/refused part keeps its plain reason visible.

import { Activity, AlertCircle, Bot, Check, Clock, Layers, Loader2, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { DelegationChildView, DelegationView } from '@/lib/agent/response-model';
import { delegationCost } from '@/lib/agent/delegation-reducer';

function humanizeAgent(agentId?: string): string {
  if (!agentId) return 'Eclipse Agent';
  return agentId
    .replace(/[-_]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatCost(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  if (value > 0 && value < 0.01) return '<$0.01';
  return `$${value.toFixed(2)}`;
}

function percentOf(child: DelegationChildView): number | null {
  if (!child.maxSteps || child.maxSteps <= 0) return null;
  if (child.step == null) return null;
  return Math.max(0, Math.min(100, Math.round((child.step / child.maxSteps) * 100)));
}

function statusLine(child: DelegationChildView): string {
  switch (child.status) {
    case 'completed':
      return 'Done';
    case 'failed':
      return child.reason ? child.reason : "Couldn't finish";
    case 'refused':
      return child.reason ? child.reason : 'Skipped';
    case 'timed_out':
      return child.reason ? child.reason : 'Ran out of time';
    case 'cancelled':
      return child.reason ? child.reason : 'Stopped';
    default:
      return child.activity || 'Starting';
  }
}

function StatusMark({ status }: { status: DelegationChildView['status'] }) {
  if (status === 'running') {
    return <Loader2 size={15} className="animate-spin text-primary" aria-hidden />;
  }
  if (status === 'completed') {
    return <Check size={15} className="text-emerald-400" aria-hidden />;
  }
  if (status === 'cancelled' || status === 'timed_out') {
    return <Clock size={15} className="text-amber-400" aria-hidden />;
  }
  return <X size={15} className="text-red-400" aria-hidden />;
}

function ChildRow({
  child,
  compact,
  winner = false,
}: {
  child: DelegationChildView;
  compact: boolean;
  winner?: boolean;
}) {
  const percent = percentOf(child);
  const running = child.status === 'running';
  const failed = child.status === 'failed' || child.status === 'refused' || child.status === 'timed_out';
  const goal = child.goal || `Part ${child.childIndex + 1}`;
  // A best-of attempt names its ANGLE ("mock the API"); the full sub-question
  // stays available in the tooltip rather than disappearing.
  const label = child.approach || goal;

  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-xl px-2.5 transition-colors',
        compact ? 'py-1.5' : 'py-2.5',
        running ? 'bg-white/[0.035]' : 'bg-white/[0.015]',
      )}
    >
      <div
        className={cn(
          'grid shrink-0 place-items-center rounded-lg ring-1',
          compact ? 'h-7 w-7' : 'h-9 w-9',
          failed ? 'bg-red-500/10 ring-red-400/20' : 'bg-white/5 ring-white/10',
        )}
      >
        <Bot size={compact ? 13 : 16} className={failed ? 'text-red-300/80' : 'text-foreground/70'} aria-hidden />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-baseline gap-1.5">
          <span
            className={cn('shrink-0 truncate font-medium text-foreground/90', compact ? 'text-[11px]' : 'text-[13px]')}
            title={humanizeAgent(child.agentId)}
          >
            {child.model || humanizeAgent(child.agentId)}
          </span>
          <span className="text-muted-foreground/50">·</span>
          <span
            className={cn('truncate text-muted-foreground', compact ? 'text-[11px]' : 'text-[12px]')}
            title={child.approach ? goal : undefined}
          >
            {label}
          </span>
          {winner && (
            <span
              className={cn(
                'shrink-0 rounded-full bg-emerald-400/15 px-1.5 py-0.5 font-medium text-emerald-300 ring-1 ring-emerald-400/20',
                compact ? 'text-[9px]' : 'text-[10px]',
              )}
            >
              Best
            </span>
          )}
        </div>
        <div className={cn('truncate text-muted-foreground/80', compact ? 'text-[10px]' : 'text-[11px]')}>
          {statusLine(child)}
        </div>
        <div
          className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-white/10"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent ?? undefined}
          aria-label={child.maxSteps ? `Step ${child.step ?? 0} of ${child.maxSteps}` : 'Progress unknown'}
        >
          <div
            className={cn(
              'h-full rounded-full transition-all duration-500',
              failed ? 'bg-red-400/70' : child.status === 'completed' ? 'bg-emerald-400/80' : 'bg-primary/80',
              percent == null && running && 'animate-pulse',
            )}
            style={{ width: percent != null ? `${percent}%` : running ? '28%' : '0%' }}
          />
        </div>
      </div>

      <div className={cn('shrink-0 text-right tabular-nums', compact ? 'w-14' : 'w-20')}>
        <div className={cn('flex items-center justify-end gap-1 text-foreground/80', compact ? 'text-[11px]' : 'text-[12px]')}>
          <StatusMark status={child.status} />
          <span>{percent != null ? `${percent}%` : ''}</span>
        </div>
        <div className={cn('text-muted-foreground', compact ? 'text-[10px]' : 'text-[11px]')}>
          {formatCost(child.costUsd)}
        </div>
      </div>
    </div>
  );
}

function DelegationCard({ delegation, compact }: { delegation: DelegationView; compact: boolean }) {
  const total = delegation.children.length;
  const done = delegation.children.filter((c) => c.status !== 'running').length;
  const anyRunning = delegation.children.some((c) => c.status === 'running');
  const { total: cost, unknown } = delegationCost(delegation.children);
  const bestOf = delegation.strategy === 'best_of';
  const title = bestOf
    ? `Best of ${total}`
    : anyRunning
      ? total === 1 ? '1 agent working' : `${total} agents working`
      : total === 1 ? '1 agent finished' : `${total} agents finished`;
  const costText = unknown ? (cost > 0 ? `≥ ${formatCost(cost)}` : '—') : formatCost(cost);
  const failed = delegation.children.some((c) => c.status === 'failed' || c.status === 'refused');

  return (
    <div className={cn('glass-card rounded-2xl border border-white/5', compact ? 'p-2' : 'p-3')}>
      <div
        className={cn('flex items-center gap-2 px-1', compact ? 'pb-1.5' : 'pb-2')}
        role="status"
        aria-live="polite"
        aria-label={`${title}, ${done} of ${total} done, ${costText}`}
      >
        <span className={cn('shrink-0', anyRunning ? 'text-primary' : failed ? 'text-amber-400' : 'text-muted-foreground/70')}>
          {anyRunning ? <Activity size={compact ? 12 : 14} className="animate-pulse" aria-hidden />
            : failed ? <AlertCircle size={compact ? 12 : 14} aria-hidden />
            : <Layers size={compact ? 12 : 14} aria-hidden />}
        </span>
        <span className={cn('min-w-0 flex-1 truncate font-medium text-foreground', compact ? 'text-[11px]' : 'text-[13px]')}>
          {title}
        </span>
        <span className={cn('shrink-0 text-muted-foreground', compact ? 'text-[10px]' : 'text-[12px]')}>
          {done} of {total} done
        </span>
        <span className={cn('shrink-0 font-medium text-foreground/80 tabular-nums', compact ? 'text-[10px]' : 'text-[12px]')}>
          {costText}
        </span>
      </div>

      <div className={compact ? 'space-y-0.5' : 'space-y-1'}>
        {delegation.children.map((child) => (
          <ChildRow
            key={child.childIndex}
            child={child}
            compact={compact}
            winner={delegation.winner === child.childIndex}
          />
        ))}
      </div>

      {delegation.droppedClaims ? (
        <div className={cn('px-1 text-muted-foreground/70', compact ? 'pt-1.5 text-[10px]' : 'pt-2 text-[11px]')}>
          {delegation.droppedClaims} statement{delegation.droppedClaims === 1 ? '' : 's'} could not be
          confirmed, so {delegation.droppedClaims === 1 ? "it isn't" : "they aren't"} repeated as fact.
        </div>
      ) : null}
    </div>
  );
}

export function ParallelAgentsPanel({
  delegations,
  compact = false,
}: {
  delegations: DelegationView[];
  compact?: boolean;
}) {
  if (!delegations || delegations.length === 0) return null;
  return (
    <div className={cn('w-full', compact ? 'mb-2 space-y-1.5' : 'mb-3 space-y-2')}>
      {delegations.map((delegation) => (
        <DelegationCard key={delegation.delegationId} delegation={delegation} compact={compact} />
      ))}
    </div>
  );
}
