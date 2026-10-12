'use client';

// ── Agent Workspace — shared presentational primitives ───────────────────────
// Small building blocks used by every workspace panel, so they stay visually
// consistent. All copy is translated; every value is passed in (never faked).

import type { ReactNode } from 'react';
import {
  Activity,
  Brain,
  Check,
  CircleDashed,
  Loader2,
  FileText,
  FlaskConical,
  Gauge,
  GitBranch,
  Globe,
  History,
  ListChecks,
  Monitor,
  MoreHorizontal,
  ScrollText,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  Wrench,
  XCircle,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { ActivityCategory, AgentStatus } from '@/lib/agent-workspace/types';

/** A labelled key/value tile. Renders "Not available" when the value is empty. */
export function StatTile({
  label,
  value,
  unavailable,
  tone = 'default',
}: {
  label: string;
  value?: ReactNode;
  /** Copy shown when there is genuinely no value ("Not available"). */
  unavailable: string;
  tone?: 'default' | 'running' | 'failed' | 'ok';
}) {
  const empty = value == null || value === '';
  return (
    <div className="glass-card-subtle rounded-xl px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">{label}</div>
      <div
        className={cn(
          'mt-0.5 truncate text-[13px] font-medium tabular-nums',
          tone === 'running' && 'text-primary',
          tone === 'failed' && 'text-rose-300',
          tone === 'ok' && 'text-emerald-300',
          empty && 'text-muted-foreground/50 font-normal',
        )}
        title={typeof value === 'string' ? value : undefined}
      >
        {empty ? unavailable : value}
      </div>
    </div>
  );
}

/** A titled section with an optional trailing count/badge. */
export function Section({
  title,
  count,
  children,
  empty,
  emptyText,
}: {
  title: string;
  count?: number;
  children?: ReactNode;
  empty: boolean;
  emptyText: string;
}) {
  return (
    <section className="space-y-1.5">
      <header className="flex items-center justify-between gap-2 px-0.5">
        <h3 className="min-w-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/70">{title}</h3>
        {count != null && count > 0 && (
          <span className="rounded-full bg-white/[0.06] px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground">
            {count}
          </span>
        )}
      </header>
      {empty ? (
        <p className="px-0.5 py-2 text-[12px] text-muted-foreground/50">{emptyText}</p>
      ) : (
        children
      )}
    </section>
  );
}

/** The colored, labelled run-status indicator (never color-only: it has text). */
export function statusTone(status: AgentStatus): 'running' | 'failed' | 'ok' | 'default' {
  if (status === 'failed') return 'failed';
  if (status === 'completed') return 'ok';
  if (status === 'planning' || status === 'running') return 'running';
  return 'default';
}

export function statusIcon(status: AgentStatus, size = 13) {
  if (status === 'running' || status === 'planning') return <Loader2 size={size} className="animate-spin" />;
  if (status === 'failed') return <XCircle size={size} />;
  if (status === 'completed') return <Check size={size} />;
  return <CircleDashed size={size} />;
}

/** The category icon for an activity row. */
export function CategoryIcon({ category, size = 13 }: { category: ActivityCategory; size?: number }) {
  switch (category) {
    case 'plan':
      return <ListChecks size={size} />;
    case 'file':
      return <FileText size={size} />;
    case 'command':
      return <Terminal size={size} />;
    case 'git':
      return <GitBranch size={size} />;
    case 'research':
      return <FlaskConical size={size} />;
    case 'browser':
      return <Globe size={size} />;
    case 'computer':
      return <Monitor size={size} />;
    case 'artifact':
      return <Sparkles size={size} />;
    case 'permission':
      return <ShieldAlert size={size} />;
    case 'context':
      return <SlidersHorizontal size={size} />;
    case 'model':
      return <Brain size={size} />;
    case 'error':
      return <XCircle size={size} />;
    case 'tool':
      return <Wrench size={size} />;
    default:
      return <Activity size={size} />;
  }
}

export const PANEL_ICONS = {
  context: Gauge,
  output: ScrollText,
  changes: FileText,
  permissions: ShieldAlert,
  history: History,
  explain: MoreHorizontal,
  overview: Activity,
  activity: Activity,
  tasks: ListChecks,
  terminal: Terminal,
  research: FlaskConical,
  browser: Globe,
  computer: Monitor,
  artifacts: Sparkles,
  telemetry: Brain,
} as const;
