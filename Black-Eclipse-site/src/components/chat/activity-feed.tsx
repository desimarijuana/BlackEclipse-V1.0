'use client';

// ── ActivityFeed — the tools/retrieval a turn used, as a collapsible group ───
// Sits above the assistant prose. Collapsed by default: one line summarising
// "Used N tools" (and any failure), so a normal answer stays uncluttered. While
// a run is live it auto-expands so the user watches the agent work; once it
// finishes it collapses back to the summary, with the details one click away.
//
// Two presentation modes share this one component:
//   compact  — the floating dock (tight rows)
//   detailed — full-page chat (roomier rows)
// Both render the same `ActivityItemRow`; only density differs.

import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Check, ChevronRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActivityItem, ResponseStatus } from '@/lib/agent/response-model';
import { ActivityItemRow } from './activity-item';

export interface ActivityFeedProps {
  activities: ActivityItem[];
  /** The live turn status — drives auto-expand and the header state. */
  status?: ResponseStatus;
  /** Tighter styling for the floating dock. */
  compact?: boolean;
  /**
   * `true` (default) auto-expands while the run is live and collapses when it
   * ends. `false` keeps it collapsed unless the user opens it.
   */
  autoExpand?: boolean;
}

/** Distinct sources/providers consulted, for the collapsed summary. */
function sourceCount(items: ActivityItem[]): number {
  const set = new Set(items.filter((a) => a.kind === 'retrieval').map((a) => a.name));
  return set.size;
}

export function ActivityFeed({ activities, status, compact = false, autoExpand = true }: ActivityFeedProps) {
  const [open, setOpen] = useState(false);
  const userToggled = useRef(false);

  const working = status === 'queued' || status === 'planning' || status === 'tool_running' || status === 'streaming';
  const failures = useMemo(() => activities.filter((a) => a.status === 'failed').length, [activities]);
  const sources = useMemo(() => sourceCount(activities), [activities]);

  // While the agent is working, show the steps; when it finishes, collapse so
  // the answer takes focus — unless the user manually opened/closed it.
  useEffect(() => {
    if (!autoExpand || userToggled.current) return;
    setOpen(working && activities.length > 0);
  }, [working, activities.length, autoExpand]);

  if (activities.length === 0) return null;

  const toggle = () => {
    userToggled.current = true;
    setOpen((v) => !v);
  };

  const summary = (() => {
    const parts: string[] = [`${activities.length} step${activities.length === 1 ? '' : 's'}`];
    if (sources > 0) parts.push(`${sources} source${sources === 1 ? '' : 's'}`);
    if (failures > 0) parts.push(`${failures} failed`);
    return parts.join(' · ');
  })();

  return (
    <div
      className={cn(
        'w-full overflow-hidden rounded-xl border border-border/40 bg-accent/[0.12]',
        compact ? 'mb-2 text-[11px]' : 'mb-3',
      )}
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-accent/30 cursor-pointer"
      >
        <span className={cn('shrink-0', working ? 'text-primary' : failures > 0 ? 'text-amber-400' : 'text-muted-foreground/70')}>
          {working ? <Loader2 size={compact ? 11 : 13} className="animate-spin" />
            : failures > 0 ? <AlertCircle size={compact ? 11 : 13} />
            : <Check size={compact ? 11 : 13} />}
        </span>
        <span className={cn('min-w-0 flex-1', compact ? 'text-[11px]' : 'text-[12px]')}>
          <span className="font-medium text-foreground">{working ? 'Working' : 'Activity'}</span>
          <span className="ml-1.5 text-muted-foreground">{summary}</span>
        </span>
        <ChevronRight
          size={compact ? 12 : 14}
          className={cn('shrink-0 text-muted-foreground/50 transition-transform', open && 'rotate-90')}
        />
      </button>

      {open && (
        <div
          className={cn(
            'border-t border-border/30',
            compact ? 'space-y-0.5 p-1.5' : 'space-y-1 p-2',
          )}
          // The feed scrolls past a long tool list rather than growing without
          // bound and pushing the answer off screen.
          style={{ maxHeight: 280, overflowY: 'auto' }}
        >
          {activities.map((item) => (
            <ActivityItemRow key={item.id} item={item} compact={compact} />
          ))}
        </div>
      )}
    </div>
  );
}
