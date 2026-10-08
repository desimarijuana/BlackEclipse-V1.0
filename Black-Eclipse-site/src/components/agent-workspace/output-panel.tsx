'use client';

// ── Agent Workspace — Output feed ─────────────────────────────────────────────
// The sidebar's default view: a chronological feed of what the agent did and
// what it produced. Each tool call / command / file write is a compact row; when
// a large output exists for it (or a produced artifact stands alone) the row
// expands IN PLACE to render the bounded content with line numbers — the
// ChatGPT / Claude Code / Kimi pattern, so a huge result never floods chat and
// never needs a separate screen.
//
// Content-free by default: collapsed rows show only label / detail / status /
// duration. The payload is fetched lazily the first time a row is expanded.

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronRight, Loader2, XCircle } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { ActivityEntry, ArtifactRef } from '@/lib/agent-workspace/types';
import { formatClock, formatDuration } from '@/lib/agent-workspace/format';
import { CategoryIcon } from './ui';
import { ArtifactContent, type LoadedContent } from './viewer';

type Row =
  | { kind: 'activity'; at: number; id: string; entry: ActivityEntry; artifact?: ArtifactRef }
  | { kind: 'artifact'; at: number; id: string; artifact: ArtifactRef };

/** A large output belongs to a step when the runtime keyed it by the same id. */
function artifactForEntry(entry: ActivityEntry, artifacts: ArtifactRef[]): ArtifactRef | undefined {
  if (entry.toolCallId) {
    const match = artifacts.find((a) => a.storageRef === entry.toolCallId || a.id.includes(entry.toolCallId as string));
    if (match) return match;
  }
  return undefined;
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

  const rows = useMemo<Row[]>(() => {
    const usedArtifacts = new Set<string>();
    const items: Row[] = [];
    for (const entry of activity) {
      const artifact = artifactForEntry(entry, artifacts);
      if (artifact) usedArtifacts.add(artifact.id);
      items.push({ kind: 'activity', at: entry.at, id: entry.id, entry, artifact });
    }
    for (const artifact of artifacts) {
      if (usedArtifacts.has(artifact.id)) continue;
      items.push({ kind: 'artifact', at: artifact.createdAt, id: artifact.id, artifact });
    }
    return items.sort((a, b) => a.at - b.at);
  }, [activity, artifacts]);

  // Keep the newest row in view unless the operator has scrolled up to read.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [rows.length]);

  if (rows.length === 0) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }

  return (
    <div
      ref={scrollRef}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
      }}
      className="h-full min-h-0 space-y-1 overflow-y-auto pr-0.5"
    >
      {rows.map((row) => (
        <OutputRow key={row.id} row={row} load={load} />
      ))}
    </div>
  );
}

function OutputRow({
  row,
  load,
}: {
  row: Row;
  load?: (artifact: ArtifactRef) => Promise<LoadedContent | null>;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);

  if (row.kind === 'artifact') {
    const { artifact } = row;
    return (
      <div className="rounded-lg border border-white/8 bg-white/[0.02]">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] hover:bg-accent/40"
        >
          <span className="shrink-0 text-muted-foreground/60">
            <CategoryIcon category="artifact" size={12} />
          </span>
          <span className="min-w-0 flex-1 truncate text-foreground/85">{artifact.name}</span>
          <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground/40">{artifact.type}</span>
          <ChevronRight size={11} className={cn('shrink-0 text-muted-foreground/30 transition-transform', open && 'rotate-90')} />
        </button>
        {open && (
          <div className="mt-0.5 max-h-[60vh] min-h-0 overflow-hidden border-t border-white/8 px-2 py-2">
            <ArtifactContent artifact={artifact} load={load} className="max-h-[58vh]" />
          </div>
        )}
      </div>
    );
  }

  const { entry, artifact } = row;
  const running = entry.status === 'running';
  const failed = entry.status === 'failed';
  const hasDetails = Boolean(entry.name || entry.code || entry.detail || entry.durationMs != null);
  const expandable = Boolean(artifact) || hasDetails;

  return (
    <div className="group/out rounded-lg">
      <button
        type="button"
        onClick={() => expandable && setOpen((v) => !v)}
        aria-expanded={expandable ? open : undefined}
        disabled={!expandable}
        className={cn(
          'flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-[12px]',
          expandable && 'cursor-pointer hover:bg-accent/40',
        )}
      >
        <span className={cn('shrink-0', failed ? 'text-rose-400' : running ? 'text-primary' : 'text-muted-foreground/60')}>
          {running ? <Loader2 size={12} className="animate-spin" /> : failed ? <XCircle size={12} /> : <CategoryIcon category={entry.category} size={12} />}
        </span>
        <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/40">{formatClock(entry.at)}</span>
        <span className="min-w-0 flex-1 truncate text-muted-foreground">
          <span className="text-foreground/80">{entry.label}</span>
          {entry.detail && <span className="ml-1.5 font-mono text-[11px] text-muted-foreground/70">{entry.detail}</span>}
        </span>
        {entry.summary && !running && <span className="shrink-0 text-[10px] text-muted-foreground/50">{entry.summary}</span>}
        {entry.durationMs != null && !running && (
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/40">{formatDuration(entry.durationMs)}</span>
        )}
        {!running && !failed && <Check size={11} className="shrink-0 text-emerald-400/60" />}
        {expandable && <ChevronRight size={11} className={cn('shrink-0 text-muted-foreground/30 transition-transform', open && 'rotate-90')} />}
      </button>
      {open && (
        <div className="ml-6 border-l border-white/10 pb-1 pl-3">
          {hasDetails && (
            <dl className="space-y-0.5 py-0.5 font-mono text-[10.5px] text-muted-foreground/70">
              {entry.name && <DetailRow label="operation" value={entry.name} />}
              {entry.category && <DetailRow label="category" value={entry.category} />}
              {entry.code && <DetailRow label="code" value={entry.code} tone="failed" />}
            </dl>
          )}
          {artifact && (
            <div className="mt-1 max-h-[60vh] min-h-0 overflow-hidden">
              <ArtifactContent artifact={artifact} load={load} className="max-h-[58vh]" />
            </div>
          )}
          {!hasDetails && !artifact && <p className="py-1 text-[11px] text-muted-foreground/40">{t('workspace.notAvailable')}</p>}
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
