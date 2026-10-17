'use client';

// ── Sidebar graph browser ───────────────────────────────────────────────────
// One pop-up that shows the two relationship graphs the app already derives:
//   • Skills  — the learning-journey provenance graph (memory ↔ skill ↔
//     correction ↔ promotion …) from `GET /api/learning/journey`.
//   • Relations — the Investor Eye relationship graph (entities + co-mention
//     edges) from the `investor-eye:graph` data-hub topic.
// Both render through the SAME ECharts force-graph idiom used elsewhere; this
// dialog only owns the fetch/tab chrome, never a second graph implementation.

import { useEffect, useMemo, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Network, Loader2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { learningJourney } from '@/lib/harness/skills-browser';
import type { LearningJourney } from '@/lib/harness/skills-types';
import { LearningGraphChart, KIND_COLOR } from '@/components/screens/skills/learning-graph';
import { RelationshipGraphChart } from '@/components/investor-eye/graph-panel';
import { useTopic } from '@/lib/workspace/data-hub';
import { IE_GRAPH_TOPIC } from '@/lib/investor-eye/topics';
import type { RelationshipGraph } from '@/lib/investor-eye/types';

type GraphTab = 'skills' | 'relations';

export function SidebarGraphDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  const [tab, setTab] = useState<GraphTab>('skills');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(85dvh,800px)] w-[calc(100vw-2rem)] max-w-none flex-col gap-0 overflow-hidden rounded-2xl border border-white/10 glass-card-strong p-0 text-foreground sm:max-w-6xl">
        <DialogHeader className="shrink-0 border-b border-border/10 px-5 py-3.5">
          <DialogTitle className="flex items-center gap-2 text-sm font-semibold">
            <Network size={15} className="text-muted-foreground" />
            {t('sidebar.graph')}
          </DialogTitle>
          <DialogDescription className="text-[11px] text-muted-foreground">
            {t('sidebar.graphDialogHint')}
          </DialogDescription>
          {/* Tab switch — restrained control-strip tier, matching the sidebar. */}
          <div className="mt-2.5 flex items-center gap-1 rounded-lg glass-card-subtle border border-border/20 p-0.5 w-fit">
            {(
              [
                { id: 'skills', label: t('sidebar.graphSkills') },
                { id: 'relations', label: t('sidebar.graphRelations') },
              ] as const
            ).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                aria-pressed={tab === item.id}
                className={cn(
                  'rounded-md px-3 py-1 text-[11px] font-semibold transition-colors cursor-pointer',
                  tab === item.id
                    ? 'bg-white/[0.1] text-foreground'
                    : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
        </DialogHeader>

        <div className="min-h-0 flex-1 p-4">
          {tab === 'skills' ? <SkillsGraph open={open} /> : <RelationsGraph open={open} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Learning-journey provenance graph — fetched imperatively (no global store). */
function SkillsGraph({ open }: { open: boolean }) {
  const t = useT();
  const [graph, setGraph] = useState<LearningJourney | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true);
    setError(null);
    learningJourney()
      .then((g) => { if (alive) setGraph(g); })
      .catch((err) => { if (alive) setError(err instanceof Error ? err.message : t('sidebar.graphUnavailable')); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [open, t]);

  const legend = useMemo(() => {
    if (!graph) return [];
    return Object.entries(graph.stats.byKind).sort((a, b) => b[1] - a[1]);
  }, [graph]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" /> {t('common.loading')}
      </div>
    );
  }
  if (error) {
    return <div className="flex h-full items-center justify-center text-xs italic text-muted-foreground/70">{error}</div>;
  }
  if (!graph || graph.nodes.length === 0) {
    return <div className="flex h-full items-center justify-center text-xs italic text-muted-foreground/70">{t('sidebar.graphEmpty')}</div>;
  }

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-[10px] text-muted-foreground/70">
          {graph.stats.nodeCount} {t('sidebar.graphNodes')} · {graph.stats.edgeCount} {t('sidebar.graphEdges')}
        </span>
        {legend.map(([kind, count]) => (
          <span
            key={kind}
            className="glass-card-subtle rounded border border-white/10 px-1.5 py-0.5 text-[9px] font-mono text-muted-foreground"
          >
            <span
              className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
              style={{ backgroundColor: KIND_COLOR[kind] ?? '#94a3b8' }}
            />
            {kind} · {count}
          </span>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        <LearningGraphChart graph={graph} className="h-full w-full" />
      </div>
    </div>
  );
}

/** Investor Eye relationship graph — served by the shared data-hub topic. */
function RelationsGraph({ open }: { open: boolean }) {
  const t = useT();
  const topic = useTopic<RelationshipGraph>(IE_GRAPH_TOPIC);
  const graph = topic.data;

  if (topic.source === 'UNAVAILABLE') {
    return <div className="flex h-full items-center justify-center text-xs italic text-muted-foreground/70">{t('sidebar.graphUnavailable')}</div>;
  }
  if (!graph || graph.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs italic text-muted-foreground/70">
        {open ? t('sidebar.graphEmpty') : ''}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-2">
      <span className="font-mono text-[10px] text-muted-foreground/70">
        {graph.nodes.length} {t('sidebar.graphNodes')} · {graph.links.length} {t('sidebar.graphEdges')}
      </span>
      <div className="min-h-0 flex-1">
        <RelationshipGraphChart graph={graph} className="h-full w-full" />
      </div>
    </div>
  );
}
