'use client';

// Restrained status pills for the Bots workspace. One visual language for
// lifecycle, live-run and health states — concise labels, small icons, and a
// limited status palette (green/amber/rose/sky/muted).

import { cn } from '@/lib/utils';
import {
  CheckCircle2,
  XCircle,
  History,
  Loader2,
  AlertTriangle,
  Pause,
  type LucideIcon,
} from '@/lib/icons';
import type { AutomationState, BreakerState, ExecutionState } from '@/lib/harness/automation-client';
import { executionLabel, executionTone, lifecycleLabel, type Tone } from '@/lib/bots/state';

const TONE_CLASS: Record<Tone, string> = {
  positive: 'text-emerald-300 border-emerald-400/25 bg-emerald-400/10',
  warning: 'text-amber-300 border-amber-400/25 bg-amber-400/10',
  danger: 'text-rose-300 border-rose-400/25 bg-rose-400/10',
  info: 'text-sky-300 border-sky-400/25 bg-sky-400/10',
  muted: 'text-muted-foreground border-border/40 bg-white/[0.03]',
};

export function StatusPill({
  tone,
  label,
  icon: Icon,
  className,
}: {
  tone: Tone;
  label: string;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold leading-none',
        TONE_CLASS[tone],
        className,
      )}
    >
      {Icon && <Icon size={11} className="shrink-0" weight="fill" />}
      {label}
    </span>
  );
}

const STATE_TONE: Record<AutomationState, Tone> = {
  draft: 'muted',
  validating: 'info',
  active: 'positive',
  paused: 'warning',
  disabled: 'muted',
  archived: 'muted',
};

export function lifecycleTone(state: AutomationState): Tone {
  return STATE_TONE[state] ?? 'muted';
}

const STATE_ICON: Record<AutomationState, LucideIcon | undefined> = {
  draft: undefined,
  validating: History,
  active: CheckCircle2,
  paused: Pause,
  disabled: undefined,
  archived: undefined,
};

export function LifecyclePill({ state }: { state: AutomationState }) {
  return <StatusPill tone={lifecycleTone(state)} label={lifecycleLabel(state)} icon={STATE_ICON[state]} />;
}

function executionIcon(state: ExecutionState): LucideIcon {
  if (state === 'completed') return CheckCircle2;
  if (state === 'failed' || state === 'timed_out') return XCircle;
  if (state === 'blocked') return AlertTriangle;
  if (state === 'running' || state === 'retrying' || state === 'queued' || state === 'triggered') return Loader2;
  return History;
}

export function ExecutionPill({ state }: { state: ExecutionState }) {
  return <StatusPill tone={executionTone(state)} label={executionLabel(state)} icon={executionIcon(state)} />;
}

export function BreakerPill({ state }: { state: BreakerState }) {
  if (state === 'closed') return null;
  if (state === 'open') {
    return <StatusPill tone="danger" label="Paused after failures" icon={AlertTriangle} />;
  }
  return <StatusPill tone="warning" label="Recovering" icon={AlertTriangle} />;
}
