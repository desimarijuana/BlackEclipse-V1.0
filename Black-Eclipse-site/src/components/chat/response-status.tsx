'use client';

// ── ResponseStatusLine — the working indicator above an assistant turn ──────
// Replaces the single generic "Thinking…" string with a state-aware line. It
// reads the typed lifecycle (not raw events) so it never claims the agent is
// thinking while it is waiting on a tool, and never keeps spinning after a
// terminal state.

import { AlertTriangle, Check, Loader2, OctagonX } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActivityItem, ResponseStatus } from '@/lib/agent/response-model';

export interface ResponseStatusLineProps {
  status: ResponseStatus;
  /** Latest activity, used to name what the agent is doing right now. */
  activities?: ActivityItem[];
  /** Tighter type for the floating dock. */
  compact?: boolean;
}

/** The label shown for each lifecycle state. */
function statusLabel(status: ResponseStatus, activities: ActivityItem[]): string {
  switch (status) {
    case 'queued':
      return 'Preparing analysis';
    case 'planning':
      return 'Reviewing available data';
    case 'tool_running': {
      const running = [...activities].reverse().find((a) => a.status === 'running');
      return running?.label ?? 'Running financial calculations';
    }
    case 'streaming':
      return 'Preparing response';
    case 'completed':
      return 'Done';
    case 'cancelled':
      return 'Stopped';
    case 'error':
      return 'Something went wrong';
  }
}

/**
 * Only `queued`/`planning`/`tool_running`/`streaming` are "working" states — the
 * indicator animates for those and resolves for the rest.
 */
function isWorking(status: ResponseStatus): boolean {
  return status === 'queued' || status === 'planning' || status === 'tool_running' || status === 'streaming';
}

export function ResponseStatusLine({ status, activities = [], compact = false }: ResponseStatusLineProps) {
  const label = statusLabel(status, activities);
  const working = isWorking(status);

  const Icon =
    status === 'completed' ? Check
    : status === 'error' ? AlertTriangle
    : status === 'cancelled' ? OctagonX
    : Loader2;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex items-center gap-1.5 font-mono',
        compact ? 'text-[10px]' : 'text-[11px]',
        status === 'error' ? 'text-rose-400'
          : status === 'cancelled' ? 'text-muted-foreground'
          : status === 'completed' ? 'text-muted-foreground/80'
          : 'text-muted-foreground',
      )}
    >
      <Icon
        size={compact ? 10 : 12}
        className={cn(
          'shrink-0',
          working && 'animate-spin text-primary',
          status === 'completed' && 'text-primary',
        )}
        aria-hidden
      />
      <span>{label}</span>
    </div>
  );
}
