'use client';

// ── Agent Workspace — Output feed ─────────────────────────────────────────────
// The sidebar's default view: a dense, chronological feed of what the agent did
// and what it produced, in the Claude Code / ChatGPT idiom. Each tool call,
// command or file write is a compact row; consecutive calls of the same tool
// GROUP into one row with a ×N count, and any row with a large output expands IN
// PLACE to render the bounded content with line numbers — so a huge result never
// floods chat and never needs a separate screen.
//
// Timestamps are hidden from the row (kept in the expanded detail) to keep the
// feed tight. A "Collapse all" control clears every open row at once.
//
// Content-free by default: collapsed rows show only icon / label / detail /
// status / duration. The payload is fetched lazily the first time a row opens.

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronRight, Loader2, XCircle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { ActivityCategory, ActivityEntry, ActivityStatus, ArtifactRef } from '@/lib/agent-workspace/types';
import { formatClock, formatDuration } from '@/lib/agent-workspace/format';
import { CategoryIcon } from './ui';
import { ArtifactContent, type LoadedContent } from './viewer';

type Item =
  | { kind: 'activity'; id: string; at: number; entry: ActivityEntry; artifact?: ArtifactRef }
  | { kind: 'artifact'; id: string; at: number; artifact: ArtifactRef };

interface Group {
  key: string;
  at: number;
  category: ActivityCategory;
  label: string;
  status: ActivityStatus;
  items: Item[];
}

/** A large output belongs to a step when the runtime keyed it by the same id. */
function artifactForEntry(entry: ActivityEntry, artifacts: ArtifactRef[]): ArtifactRef | undefined {
  if (entry.toolCallId) {
    const match = artifacts.find((a) => a.storageRef === entry.toolCallId || a.id.includes(entry.toolCallId as string));
    if (match) return match;
  }
  return undefined;
}

/** Consecutive same-tool activities share a group key; standalone artifacts do not. */
function groupKey(item: Item): string {
  if (item.kind === 'artifact') return `z:${item.id}`;
  return `a:${item.entry.category}:${item.entry.name ?? item.entry.label}`;
}

/** A running row never merges into a neighbour (it is the live tail). */
function groupable(item: Item): boolean {
  return item.kind === 'activity' && item.entry.status !== 'running';
}

function worstStatus(items: Item[]): ActivityStatus {
  let status: ActivityStatus = 'completed';
  for (const item of items) {
    const s = item.kind === 'activity' ? item.entry.status : 'completed';
    if (s === 'failed') return 'failed';
    if (s === 'running') status = 'running';
  }
  return status;
}

export function OutputPanel({
  activity,
  artifacts,
  load,
}: {
  activity: ActivityEntry[];
  artifacts: ArtifactRef[];
  load?: (artifact: ArtifactRef) => Promise<LoadedContent | null>;
}) {
  const t = useT();
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [openKeys, setOpenKeys] = useState<ReadonlySet<string>>(() => new Set());

  const groups = useMemo<Group[]>(() => {
    const usedArtifacts = new Set<string>();
    const items: Item[] = [];
    for (const entry of activity) {
      const artifact = artifactForEntry(entry, artifacts);
      if (artifact) usedArtifacts.add(artifact.id);
      items.push({ kind: 'activity', id: entry.id, at: entry.at, entry, artifact });
    }
    for (const artifact of artifacts) {
      if (usedArtifacts.has(artifact.id)) continue;
      items.push({ kind: 'artifact', id: artifact.id, at: artifact.createdAt, artifact });
    }
    items.sort((a, b) => a.at - b.at);

    const out: Group[] = [];
    let current: Group | null = null;
    for (const item of items) {
      const key = groupKey(item);
      if (current && current.key === key && groupable(item)) {
        current.items.push(item);
        current.status = worstStatus(current.items);
        continue;
      }
      const category = item.kind === 'activity' ? item.entry.category : 'artifact';
      const label = item.kind === 'activity' ? item.entry.label : item.artifact.name;
      current = { key: item.id, at: item.at, category, label, status: worstStatus([item]), items: [item] };
      out.push(current);
    }
    return out;
  }, [activity, artifacts]);

  // Keep the newest row in view unless the operator has scrolled up to read.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [groups.length]);

  const toggle = (key: string) =>
    setOpenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  if (groups.length === 0) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-0.5 flex shrink-0 items-center justify-between px-0.5">
        <span className="text-[10px] tabular-nums text-muted-foreground/40">
          {groups.length.toLocaleString()} {t('workspace.actions')}
        </span>
        {openKeys.size > 0 && (
          <button
            type="button"
            onClick={() => setOpenKeys(new Set())}
            className="rounded-md px-1.5 py-0.5 text-[10px] text-muted-foreground/60 transition-colors hover:bg-white/[0.05] hover:text-foreground"
          >
            {t('workspace.collapseAll')}
          </button>
        )}
      </div>
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        className="min-h-0 flex-1 space-y-0.5 overflow-y-auto pr-0.5"
      >
        {groups.map((group) => (
          <OutputRow key={group.key} group={group} load={load} open={openKeys.has(group.key)} onToggle={toggle} />
        ))}
      </div>
    </div>
  );
}

function OutputRow({
  group,
  load,
  open,
  onToggle,
}: {
  group: Group;
  load?: (artifact: ArtifactRef) => Promise<LoadedContent | null>;
  open: boolean;
  onToggle: (key: string) => void;
}) {
  const t = useT();
  const only = group.items[0];
  const single = group.items.length === 1;
  const artifact = !single ? undefined : only.kind === 'activity' ? only.artifact : only.artifact;
  const entry = !single || only.kind !== 'activity' ? undefined : only.entry;

  const running = single ? group.status === 'running' : false;
  const failed = group.status === 'failed';
  const summary = single && entry ? entry.summary : undefined;
  const durationMs = single && entry ? entry.durationMs : undefined;
  const detail = single && entry ? entry.detail : undefined;
  const hasDetails = Boolean(entry && (entry.name || entry.code || entry.detail || entry.durationMs != null));
  const expandable = Boolean(artifact) || hasDetails || !single;

  return (
    <div className="group/out rounded-lg">
      <button
        type="button"
        onClick={() => expandable && onToggle(group.key)}
        aria-expanded={expandable ? open : undefined}
        disabled={!expandable}
        className={cn(
          'flex w-full items-center gap-1.5 rounded-lg px-2 py-0.5 text-left text-[12px]',
          expandable && 'cursor-pointer hover:bg-accent/40',
        )}
      >
        <span className={cn('shrink-0', failed ? 'text-rose-400' : running ? 'text-primary' : 'text-muted-foreground/55')}>
          {running ? <Loader2 size={12} className="animate-spin" /> : failed ? <XCircle size={12} /> : <CategoryIcon category={group.category} size={12} />}
        </span>
        <span className="min-w-0 flex-1 truncate text-muted-foreground">
          <span className="text-foreground/80">{entry ? entry.label : group.label}</span>
          {detail && <span className="ml-1.5 truncate font-mono text-[11px] text-muted-foreground/70">{detail}</span>}
        </span>
        {!single && (
          <span className="shrink-0 rounded-full bg-white/[0.06] px-1.5 text-[10px] tabular-nums text-muted-foreground/60">×{group.items.length}</span>
        )}
        {summary && !running && <span className="shrink-0 text-[10px] text-muted-foreground/50">{summary}</span>}
        {durationMs != null && !running && (
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/40">{formatDuration(durationMs)}</span>
        )}
        {!running && !failed && <Check size={11} className="shrink-0 text-emerald-400/60" />}
        {expandable && <ChevronRight size={11} className={cn('shrink-0 text-muted-foreground/30 transition-transform', open && 'rotate-90')} />}
      </button>

      {open && (
        <div className="ml-5 border-l border-white/10 pb-0.5 pl-2.5">
          {single && entry && (
            <dl className="space-y-0.5 py-0.5 font-mono text-[10.5px] text-muted-foreground/70">
              <DetailRow label="at" value={formatClock(entry.at)} />
              {entry.name && <DetailRow label="operation" value={entry.name} />}
              {entry.category && <DetailRow label="category" value={entry.category} />}
              {entry.code && <DetailRow label="code" value={entry.code} tone="failed" />}
            </dl>
          )}
          {!single && (
            <ul className="space-y-px py-0.5">
              {group.items.map((item) => (
                <li key={item.id} className="flex items-baseline gap-1.5 text-[11.5px] text-muted-foreground/80">
                  <span className="shrink-0 text-muted-foreground/35">·</span>
                  <span className="min-w-0 flex-1 truncate">
                    {item.kind === 'activity'
                      ? (item.entry.detail ?? item.entry.name ?? item.entry.label)
                      : item.artifact.name}
                  </span>
                  {item.kind === 'activity' && item.entry.summary && (
                    <span className="shrink-0 text-[10px] text-muted-foreground/50">{item.entry.summary}</span>
                  )}
                  {item.kind === 'activity' && item.entry.durationMs != null && (
                    <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/40">{formatDuration(item.entry.durationMs)}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {artifact && (
            <div className="mt-1 max-h-[60vh] min-h-0 overflow-hidden">
              <ArtifactContent artifact={artifact} load={load} className="max-h-[58vh]" />
            </div>
          )}
          {single && !hasDetails && !artifact && <p className="py-1 text-[11px] text-muted-foreground/40">{t('workspace.notAvailable')}</p>}
        </div>
      )}
    </div>
  );
}

function DetailRow({ label, value, tone }: { label: string; value: string; tone?: 'failed' }) {
  return (
    <div className="flex gap-2">
      <dt className="shrink-0 text-muted-foreground/40">{label}</dt>
      <dd className={cn('break-all', tone === 'failed' && 'text-rose-300/90')}>{value}</dd>
    </div>
  );
}
