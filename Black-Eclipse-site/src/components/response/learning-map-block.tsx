'use client';

// ── Interactive learning-map block ───────────────────────────────────────────
// Renders a real, prerequisite-aware learning roadmap built by the learning
// engine (never a generated image). It is the one response block with WRITE
// interactivity: a completion toggle persists through the existing
// `/api/learning/progress` route (which reaches the SAME durable store the agent
// writes through), and resource links open the real resource. An "alternatives"
// action re-enters the EXISTING agent loop via `onFollowup` — no decorative
// controls, no privileged backend calls.

import { useCallback, useMemo, useRef, useState } from 'react';
import {
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  ExternalLink,
  GraduationCap,
  ListChecks,
  Sparkles,
  AlertCircle,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { NoticeCard } from './blocks';
import type { LearningMapBlock as LearningMapBlockType, LearningNode, LearningResourceRef } from '@/lib/response/contract';

type NodeStatus = 'pending' | 'in_progress' | 'completed' | 'skipped';

const LEVEL_TONE: Record<string, string> = {
  beginner: 'text-emerald-300 ring-emerald-500/30',
  intermediate: 'text-sky-300 ring-sky-500/30',
  advanced: 'text-violet-300 ring-violet-500/30',
  unspecified: 'text-muted-foreground ring-border/40',
};

const STATUS_LABEL: Record<NodeStatus, string> = {
  pending: 'Not started',
  in_progress: 'In progress',
  completed: 'Completed',
  skipped: 'Skipped',
};

/** Lay out nodes into prerequisite "levels" (longest-path from a root). */
function layoutLevels(nodes: LearningNode[]): { levels: string[][]; depth: Record<string, number> } {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const depth: Record<string, number> = {};
  const visiting = new Set<string>();
  const compute = (id: string): number => {
    if (depth[id] !== undefined) return depth[id];
    if (visiting.has(id)) return 0; // cycle guard (validation already flagged it)
    visiting.add(id);
    const node = byId.get(id);
    const reqs = (node?.requires ?? []).filter((r) => byId.has(r));
    const d = reqs.length === 0 ? 0 : Math.max(...reqs.map(compute)) + 1;
    visiting.delete(id);
    depth[id] = d;
    return d;
  };
  for (const n of nodes) compute(n.id);
  const maxDepth = Math.max(0, ...Object.values(depth));
  const levels: string[][] = Array.from({ length: maxDepth + 1 }, () => []);
  for (const n of nodes) levels[depth[n.id]].push(n.id);
  return { levels, depth };
}

function formatDuration(seconds?: number): string | null {
  if (!seconds || seconds <= 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0) return `${h}h${m ? ` ${m}m` : ''}`;
  return `${m}m`;
}

export function LearningMapBlock({
  block,
  onFollowup,
}: {
  block: LearningMapBlockType;
  onFollowup?: (prompt: string) => void;
}) {
  const resources = useMemo(() => {
    const map = new Map<string, LearningResourceRef>();
    for (const r of block.resources) map.set(r.resourceId, r);
    return map;
  }, [block.resources]);

  const [status, setStatus] = useState<Record<string, NodeStatus>>(() => {
    const init: Record<string, NodeStatus> = {};
    for (const n of block.nodes) init[n.id] = n.status as NodeStatus;
    return init;
  });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const saving = useRef<Set<string>>(new Set());

  const persist = useCallback(
    async (nodeId: string, next: NodeStatus) => {
      if (!block.pathId) return;
      const key = `${block.pathId}:${nodeId}`;
      if (saving.current.has(key)) return;
      saving.current.add(key);
      try {
        const res = await fetch('/api/learning/progress', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pathId: block.pathId, nodeId, status: next }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setSaveError(null);
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : 'save failed');
      } finally {
        saving.current.delete(key);
      }
    },
    [block.pathId],
  );

  const toggle = useCallback(
    (nodeId: string) => {
      setStatus((prev) => {
        const cur = prev[nodeId] ?? 'pending';
        const next: NodeStatus = cur === 'completed' ? 'pending' : 'completed';
        void persist(nodeId, next);
        return { ...prev, [nodeId]: next };
      });
    },
    [persist],
  );

  const { levels, depth } = useMemo(() => layoutLevels(block.nodes), [block.nodes]);
  const completedCount = block.nodes.filter((n) => status[n.id] === 'completed').length;
  const totalHours = block.nodes.reduce((sum, n) => sum + (n.estimatedHours ?? 0), 0);

  return (
    <section className="glass-card my-2 rounded-2xl p-3 sm:p-4" aria-label={block.title || 'Learning roadmap'}>
      <header className="mb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <GraduationCap size={16} className="text-primary" />
              {block.title || (block.goal ? `Learning map: ${block.goal}` : 'Learning map')}
            </h3>
            {block.goal && block.title ? <p className="mt-0.5 text-[12px] text-muted-foreground">{block.goal}</p> : null}
            {block.targetCompetency ? (
              <p className="mt-0.5 text-[11px] text-muted-foreground/80">Target: {block.targetCompetency}</p>
            ) : null}
          </div>
          <div className="shrink-0 text-right">
            <div className="text-[11px] text-muted-foreground">
              {completedCount}/{block.nodes.length} complete
            </div>
            {totalHours > 0 ? <div className="text-[10px] text-muted-foreground/60">~{Math.round(totalHours)}h est.</div> : null}
          </div>
        </div>
        {block.startLevel && block.startLevel !== 'unspecified' ? (
          <span className={cn('mt-1 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] ring-1', LEVEL_TONE[block.startLevel])}>
            starts {block.startLevel}
          </span>
        ) : null}
        {!block.pathId ? (
          <p className="mt-1 text-[10px] text-muted-foreground/60">
            Progress isn&apos;t persisted for this map (no saved path id).
          </p>
        ) : null}
        {saveError ? (
          <p className="mt-1 flex items-center gap-1 text-[10px] text-rose-300">
            <AlertCircle size={11} /> Could not save progress: {saveError}
          </p>
        ) : null}
      </header>

      {block.issues.length > 0 ? (
        <NoticeCard
          tone="warning"
          icon={AlertCircle}
          dense
          className="mb-3"
          title={<span className="text-[11px]">{block.issues.length} curriculum gap(s)</span>}
        >
          <ul className="mt-0.5 list-disc pl-4 text-[10px] text-foreground/70">
            {block.issues.slice(0, 6).map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        </NoticeCard>
      ) : null}

      <div className="flex snap-x gap-2.5 overflow-x-auto pb-1">
        {levels.map((ids, levelIdx) => (
          <div key={levelIdx} className="min-w-[240px] max-w-[320px] flex-1 shrink-0 snap-start">
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
                Stage {levelIdx + 1}
              </span>
              <div className="h-px flex-1 bg-border/40" />
            </div>
            <div className="flex flex-col gap-2">
              {ids.map((id) => {
                const node = block.nodes.find((n) => n.id === id)!;
                return (
                  <LearningNodeCard
                    key={id}
                    node={node}
                    status={status[id] ?? 'pending'}
                    expanded={!!expanded[id]}
                    onToggleExpand={() => setExpanded((p) => ({ ...p, [id]: !p[id] }))}
                    onToggleComplete={() => toggle(id)}
                    resources={resources}
                    depth={depth[id]}
                    onFindAlternatives={
                      onFollowup
                        ? () => onFollowup(`Find alternative free resources for the skill "${node.label}" in the context of: ${block.goal ?? 'the learning goal'}`)
                        : undefined
                    }
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <details className="mt-3 text-[11px] text-muted-foreground">
        <summary className="cursor-pointer select-none text-muted-foreground/70">Text outline</summary>
        <ol className="mt-1.5 list-decimal space-y-0.5 pl-5">
          {block.nodes.map((n) => (
            <li key={n.id}>
              <span className={status[n.id] === 'completed' ? 'line-through opacity-60' : ''}>{n.label}</span>
              {n.requires.length > 0 ? <span className="text-muted-foreground/50"> (after {n.requires.join(', ')})</span> : null}
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}

function LearningNodeCard({
  node,
  status,
  expanded,
  onToggleExpand,
  onToggleComplete,
  resources,
  depth,
  onFindAlternatives,
}: {
  node: LearningNode;
  status: NodeStatus;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleComplete: () => void;
  resources: Map<string, LearningResourceRef>;
  depth: number;
  onFindAlternatives?: () => void;
}) {
  const nodeResources = node.resourceIds.map((rid) => resources.get(rid)).filter(Boolean) as LearningResourceRef[];
  const done = status === 'completed';

  return (
    <div className={cn('glass-card-subtle rounded-xl p-2.5 transition-colors', done && 'ring-1 ring-emerald-500/30')}>
      <button
        type="button"
        onClick={onToggleComplete}
        aria-pressed={done}
        className="flex w-full items-start gap-2 text-left"
        title={blockPathTitle(node)}
      >
        {done ? (
          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-400" />
        ) : (
          <CircleDot size={16} className="mt-0.5 shrink-0 text-muted-foreground/50" />
        )}
        <span className="min-w-0 flex-1">
          <span className={cn('block text-[12px] font-medium text-foreground', done && 'line-through opacity-70')}>
            {node.label}
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <span className={cn('rounded-full px-1.5 py-0.5 text-[9px] ring-1', LEVEL_TONE[node.level])}>{node.level}</span>
            {node.milestone ? (
              <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] text-primary">{node.milestone}</span>
            ) : null}
            <span className="text-[9px] text-muted-foreground/60">{STATUS_LABEL[status]}</span>
          </span>
        </span>
      </button>

      {nodeResources.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {nodeResources.map((r) => (
            <li key={r.resourceId}>
              <a
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-start gap-1.5 rounded-lg px-1.5 py-1 hover:bg-muted/40"
              >
                {r.thumbnail ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={r.thumbnail} alt="" className="h-8 w-14 shrink-0 rounded object-cover" loading="lazy" />
                ) : (
                  <ListChecks size={13} className="mt-0.5 shrink-0 text-muted-foreground/60" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1 text-[11px] text-foreground group-hover:text-primary">
                    <span className="truncate">{r.title}</span>
                    <ExternalLink size={10} className="shrink-0 opacity-60" />
                  </span>
                  <span className="flex flex-wrap items-center gap-1 text-[9px] text-muted-foreground/60">
                    {r.type ? <span>{r.type}</span> : null}
                    {formatDuration(r.durationSeconds) ? <span>· {formatDuration(r.durationSeconds)}</span> : null}
                    {r.cost && r.cost !== 'unknown' ? <span>· {r.cost}</span> : null}
                  </span>
                  {r.reason ? <span className="mt-0.5 block text-[9px] text-muted-foreground/50">{r.reason}</span> : null}
                </span>
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1.5 pl-6 text-[10px] text-muted-foreground/50">No verified resource attached — a stated gap.</p>
      )}

      {(node.objectives.length > 0 || node.exercises.length > 0 || node.project || node.assessment || node.detail) && (
        <>
          <button
            type="button"
            onClick={onToggleExpand}
            aria-expanded={expanded}
            className="mt-1.5 flex items-center gap-1 pl-6 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <ChevronDown size={11} className={cn('transition-transform', expanded && 'rotate-180')} />
            {expanded ? 'Hide details' : 'Objectives, exercises & assessment'}
          </button>
          {expanded ? (
            <div className="mt-1.5 space-y-1.5 pl-6 pr-1">
              {node.detail ? <p className="text-[10px] text-muted-foreground/80">{node.detail}</p> : null}
              <DetailList label="Objectives" items={node.objectives} />
              <DetailList label="Exercises" items={node.exercises} />
              {node.project ? <DetailLine label="Project" value={node.project} /> : null}
              {node.assessment ? <DetailLine label="Assessment" value={node.assessment} /> : null}
              {node.estimatedHours ? <DetailLine label="Est. time" value={`~${node.estimatedHours}h`} /> : null}
            </div>
          ) : null}
        </>
      )}

      {onFindAlternatives ? (
        <button
          type="button"
          onClick={onFindAlternatives}
          className="mt-1.5 flex items-center gap-1 pl-6 text-[10px] text-primary/80 hover:text-primary"
        >
          <Sparkles size={11} /> Find alternatives
        </button>
      ) : null}
      {depth > 0 ? <span className="sr-only">stage {depth + 1}</span> : null}
    </div>
  );
}

function DetailList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <span className="flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground/60">
        <Check size={9} /> {label}
      </span>
      <ul className="mt-0.5 list-disc pl-4 text-[10px] text-muted-foreground/80">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  );
}

function DetailLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-[10px] text-muted-foreground/80">
      <span className="font-semibold uppercase tracking-wide text-muted-foreground/60">{label}: </span>
      {value}
    </div>
  );
}

function blockPathTitle(node: LearningNode): string {
  return node.assessment ? `${node.label} — assessment: ${node.assessment}` : node.label;
}
