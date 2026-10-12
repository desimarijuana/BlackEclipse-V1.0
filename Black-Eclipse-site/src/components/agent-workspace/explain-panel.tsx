'use client';

// ── Agent Workspace — Influences panel ───────────────────────────────────────
// "Why did the agent know/use this?" — the run's memory/skill observability,
// relocated from the inline chat turn into the docked right sidebar so it reads
// like the other run panels. It fetches on demand from
// `GET /api/harness/runs/{id}/explain`, changes nothing at runtime, and redacts
// secret-shaped content (the runtime already does the redaction). An unreported
// value is never faked; an unavailable endpoint renders its error honestly.

import { useEffect, useState } from 'react';
import { Loader2 } from '@/lib/icons';
import { useT } from '@/lib/i18n';
import { Section, StatTile } from './ui';

interface Explanation {
  memory?: {
    injected?: Array<{ id: string }>;
    excluded?: Array<{ id: string; reason: string; category: string }>;
    budget?: { usedChars?: number; budgetChars?: number };
    selectionReasons?: string[];
  };
  profile?: { snapshotId?: string; entries?: number; charCount?: number; tokenEstimate?: number; excluded?: number } | null;
  promptPlan?: { cacheKey?: string; reusableTokens?: number; segments?: Array<{ id: string; source: string; chars?: number; tokenEstimate?: number }> } | null;
  skills?: { bundleId?: string; resolved?: string[]; missing?: string[]; unavailable?: string[]; provenance?: string } | null;
  /** Workflow step tree + per-step tool scope (Harness closeout Phase 7). */
  workflow?: {
    workflowId?: string | null;
    steps?: Array<{ stepId?: string; kind?: string; status?: string; scope?: string[]; runId?: string }>;
  } | null;
  /** Run lineage: parent chain + children (Phase 1/7). */
  lineage?: { runId?: string; parentRunId?: string | null; parents?: Array<{ id: string; status?: string | null }>; children?: string[] } | null;
  /** The checkpoint a killed-and-resumed run resumed from (Phase 7). */
  resumed?: { checkpointId?: string; step?: number } | null;
  note?: string;
}

/** Coarse category → short, plain-English heading. */
const CATEGORY_LABELS: Record<string, string> = {
  scope: 'Out of scope',
  status: 'Not active',
  expiry: 'Expired',
  permissions: 'Not permitted',
  relevance: 'Not relevant',
  budget: 'Over budget',
  trust: 'Low trust',
  drift: 'Quarantined',
  other: 'Other',
};

/** Raw exclusion reason → plain-English sentence. Falls back to the original. */
function friendlyReason(reason: string): string {
  const text = (reason || '').toLowerCase();
  if (text === 'user scope not attributable') return 'Personal memory, but no signed-in user to attribute it to';
  if (text === "another user's scope") return 'Belongs to a different user';
  if (text === 'recall denied by policy') return 'Recall is turned off for this memory type';
  if (text === 'proposed (needs review)') return 'Suggested memory, still awaiting your review';
  if (text === 'expired') return 'Past its retention date';
  if (text === 'low confidence, unverified') return 'Low confidence and never verified';
  if (text === 'no lexical relevance to query') return 'Not related to this question';
  if (text === 'rank limit') return 'Further down the ranking than the limit allows';
  if (text === 'over context budget') return 'Would push the memory context over budget';
  if (text.startsWith('status=')) return `Replaced or retired (${reason.slice('status='.length)})`;
  if (text.startsWith('scope ') && text.endsWith(' not authorized')) return 'Scope not authorized for this run';
  return reason || 'Filtered out';
}

/** Group exclusions by category, counting identical reasons within each. */
function groupExclusions(excluded: Array<{ id: string; reason: string; category: string }>) {
  const groups = new Map<string, Map<string, number>>();
  for (const e of excluded) {
    const cat = e.category || 'other';
    if (!groups.has(cat)) groups.set(cat, new Map());
    const reasons = groups.get(cat)!;
    reasons.set(e.reason, (reasons.get(e.reason) ?? 0) + 1);
  }
  return [...groups.entries()].map(([category, reasons]) => ({
    category,
    label: CATEGORY_LABELS[category] ?? category,
    total: [...reasons.values()].reduce((a, b) => a + b, 0),
    reasons: [...reasons.entries()].sort((a, b) => b[1] - a[1]),
  }));
}

export function ExplainPanel({ runId }: { runId: string | null }) {
  const t = useT();
  const notAvailable = t('workspace.notAvailable');

  const [data, setData] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    fetch(`/api/harness/runs/${encodeURIComponent(runId)}/explain`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Explanation unavailable (${res.status})`);
        return (await res.json()) as Explanation;
      })
      .then((json) => {
        if (!cancelled) setData(json);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (!runId) {
    return <p className="px-0.5 py-2 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }

  if (loading) {
    return (
      <p className="flex items-center gap-1.5 px-0.5 py-2 text-[12px] text-muted-foreground">
        <Loader2 size={12} className="animate-spin" /> Loading…
      </p>
    );
  }

  if (error) {
    return <p className="px-0.5 py-2 text-[12px] text-rose-300">{error}</p>;
  }

  if (!data) return null;

  const injected = data.memory?.injected?.length ?? 0;
  const excluded = data.memory?.excluded?.length ?? 0;
  const groups = data.memory?.excluded ? groupExclusions(data.memory.excluded) : [];

  const usedChars = data.memory?.budget?.usedChars;
  const budgetChars = data.memory?.budget?.budgetChars;
  const budgetPct = usedChars != null && budgetChars ? Math.min(100, Math.round((usedChars / budgetChars) * 100)) : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        <StatTile label="Used in this answer" unavailable={notAvailable} value={String(injected)} tone="running" />
        <StatTile label="Filtered out" unavailable={notAvailable} value={String(excluded)} />
      </div>

      {injected > 0 && (
        <Section title="Memories the agent had available" count={injected} empty={false} emptyText={t('workspace.empty')}>
          <div className="flex flex-wrap gap-1 px-0.5">
            {data.memory?.injected?.map((m) => (
              <span key={m.id} className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary/90" title={m.id}>
                {m.id.slice(0, 18)}
              </span>
            ))}
          </div>
        </Section>
      )}

      {groups.length > 0 && (
        <Section
          title={`Why ${excluded} ${excluded === 1 ? 'memory was' : 'memories were'} filtered out`}
          count={excluded}
          empty={false}
          emptyText={t('workspace.empty')}
        >
          <div className="space-y-2 px-0.5">
            {groups.map((g) => (
              <div key={g.category}>
                <p className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-amber-300/90">
                  {g.label}
                  <span className="rounded-full bg-amber-400/10 px-1.5 text-[10px] text-amber-200/80">{g.total}</span>
                </p>
                <ul className="mt-0.5 space-y-0.5 text-[11.5px] text-muted-foreground">
                  {g.reasons.map(([reason, count]) => (
                    <li key={reason} className="flex items-start gap-1.5">
                      <span className="mt-[5px] h-1 w-1 shrink-0 rounded-full bg-muted-foreground/40" />
                      <span className="flex-1">{friendlyReason(reason)}</span>
                      {count > 1 && <span className="shrink-0 text-muted-foreground/60">×{count}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      )}

      {budgetPct != null && (
        <Section title="Memory budget" empty={false} emptyText={t('workspace.empty')}>
          <div className="space-y-1 px-0.5">
            <div className="flex items-center justify-between gap-2 text-[11.5px]">
              <span className="text-muted-foreground">
                {(usedChars ?? 0).toLocaleString()} / {(budgetChars ?? 0).toLocaleString()} chars
              </span>
              <span className="shrink-0 tabular-nums text-foreground/80">{budgetPct}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
              <div className="h-full rounded-full bg-primary/60" style={{ width: `${budgetPct}%` }} />
            </div>
            <p className="text-[10.5px] text-muted-foreground/70">
              Caps how much remembered context can enter one prompt; everything past it is filtered out.
            </p>
          </div>
        </Section>
      )}

      <div className="space-y-4">
        {(data.workflow?.steps?.length || data.lineage?.parents?.length || data.lineage?.children?.length || data.resumed) && (
          <Section title="Workflow & lineage" empty={false} emptyText={t('workspace.empty')}>
            <div className="space-y-0.5 px-0.5 text-[11.5px] text-muted-foreground">
              {data.workflow?.workflowId && <p className="break-words">Workflow: {data.workflow.workflowId}</p>}
              {data.workflow?.steps?.map((s, i) => (
                <p key={`${s.stepId}-${i}`} className="break-words">
                  Step {s.stepId} ({s.kind}): {s.status ?? 'pending'}
                  {s.scope?.length ? ` · tools: ${s.scope.join(', ')}` : ''}
                </p>
              ))}
              {data.lineage?.parentRunId && <p className="break-words">Parent run: {data.lineage.parentRunId}</p>}
              {data.lineage?.parents?.length ? <p className="break-words">Ancestry: {data.lineage.parents.map((p) => p.id).join(' → ')}</p> : null}
              {data.lineage?.children?.length ? <p className="break-words">Child runs: {data.lineage.children.join(', ')}</p> : null}
              {data.resumed && <p className="break-words">Resumed from checkpoint {data.resumed.checkpointId ?? '—'} at step {data.resumed.step ?? '?'}</p>}
            </div>
          </Section>
        )}

        {(data.profile || data.skills || data.promptPlan?.segments?.length) && (
          <Section title="Also shaping the prompt" empty={false} emptyText={t('workspace.empty')}>
            <div className="space-y-0.5 px-0.5 text-[11.5px] text-muted-foreground">
              {data.profile && (
                <p className="break-words">
                  Profile: {data.profile.entries ?? 0} {data.profile.entries === 1 ? 'fact' : 'facts'} · {(data.profile.charCount ?? 0).toLocaleString()} chars
                  {data.profile.excluded ? ` · ${data.profile.excluded} filtered` : ''}
                </p>
              )}
              {data.skills && (
                <p className="break-words">
                  Skills: {(data.skills.resolved ?? []).join(', ') || 'none resolved'}
                  {data.skills.missing?.length ? ` · missing ${data.skills.missing.join(', ')}` : ''}
                </p>
              )}
              {data.promptPlan?.segments?.length ? <p className="break-words">Prompt sections: {data.promptPlan.segments.map((s) => s.id).join(', ')}</p> : null}
            </div>
          </Section>
        )}
      </div>

      <p className="px-0.5 text-[10.5px] text-muted-foreground/60">
        {data.note ?? "Derived from this run's retrieval and run events; read-only."}
      </p>
    </div>
  );
}
