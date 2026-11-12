'use client';

// ── Research screen widgets ──────────────────────────────────────────────────
// The widget bodies behind the dedicated Research screen. They consume the ONE
// research state hook (`useResearchScreen`) — no second fetch path, no
// fabricated data. A run that has not produced evidence shows an honest empty
// state; a background run shows live progress.

import React from 'react';
import { cn } from '@/lib/utils';
import { Database, Loader2, Play, Zap } from '@/lib/icons';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import type { ResearchScreenState } from '@/lib/research/use-research-screen';
import type { ResearchEvidenceRow } from '@/lib/research/research-client';

export const RESEARCH_FRAME_HEIGHT: Record<string, number> = {
  'research-evidence': 380,
  'research-claims': 360,
  'research-conflicts': 300,
  'research-runs': 340,
};

export const RESEARCH_MIN_HEIGHT: Record<string, number> = {
  'research-run-form': 260,
  'research-answer': 300,
  'research-schedule': 260,
  'research-graph': 360,
};

export function researchSizing(widgetId: string): { defaultHeight?: number; minHeight?: number } {
  return {
    defaultHeight: RESEARCH_FRAME_HEIGHT[widgetId],
    minHeight: RESEARCH_MIN_HEIGHT[widgetId],
  };
}

const TERMINAL = new Set(['COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED']);

function WidgetHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2 border-b border-border/10 pb-2.5">
      <h3 className="truncate font-serif text-sm font-semibold text-foreground">{title}</h3>
      {hint && <span className="shrink-0 font-mono text-[9px] text-muted-foreground/70">{hint}</span>}
    </div>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center py-8 text-center">
      <p className="text-xs italic text-muted-foreground/70">{children}</p>
    </div>
  );
}

function stateTone(state: string | null | undefined): string {
  if (!state) return 'text-muted-foreground';
  if (TERMINAL.has(state)) {
    return state === 'COMPLETED' ? 'text-emerald-400' : state === 'FAILED' ? 'text-rose-400' : 'text-amber-400';
  }
  return 'text-sky-400';
}

// ── Run list + start form ────────────────────────────────────────────────────

function RunsWidget({ state }: { state: ResearchScreenState }) {
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Research Runs" hint={`${state.runs.length}`} />
      {state.loadingList ? (
        <EmptyNote>Loading runs…</EmptyNote>
      ) : state.runs.length === 0 ? (
        <EmptyNote>No research runs yet — start one from the form.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {state.runs.map((r) => (
            <button
              key={r.researchId}
              onClick={() => state.select(r.researchId)}
              className={cn(
                'rounded-lg border px-2.5 py-2 text-left transition-colors cursor-pointer',
                state.selectedId === r.researchId
                  ? 'border-primary/40 bg-primary/10'
                  : 'border-border/10 glass-card-subtle hover:border-border/30',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[11px] text-foreground">{r.question}</span>
                <span className={cn('shrink-0 font-mono text-[9px] uppercase', stateTone(r.state))}>{r.state}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 font-mono text-[9px] text-muted-foreground">
                {r.intent && <span className="capitalize">{r.intent}</span>}
                {r.depth && <span>· {r.depth}</span>}
                {r.updatedAt && <span className="truncate">· {r.updatedAt.slice(0, 16).replace('T', ' ')}</span>}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function StartFormWidget({ state }: { state: ResearchScreenState }) {
  const [question, setQuestion] = React.useState('');
  const [depth, setDepth] = React.useState('STANDARD');
  const [primary, setPrimary] = React.useState(false);
  const [crossValidate, setCrossValidate] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const submit = React.useCallback(async () => {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    const id = await state.start({
      question: q,
      depth,
      primarySourcesRequired: primary,
      crossValidationRequired: crossValidate,
    });
    setBusy(false);
    if (id) setQuestion('');
  }, [question, depth, primary, crossValidate, busy, state]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="New Research" hint="BACKGROUND" />
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="e.g. NVIDIA's data-center revenue growth and competitive risks"
        rows={3}
        className="w-full resize-none rounded-lg border border-border/30 bg-transparent px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary/40 focus:outline-none"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          value={depth}
          onChange={(e) => setDepth(e.target.value)}
          className="h-8 rounded-lg border border-border/30 bg-transparent px-2 text-[11px] text-foreground focus:outline-none"
        >
          <option value="QUICK">Quick</option>
          <option value="STANDARD">Standard</option>
          <option value="DEEP">Deep</option>
        </select>
        <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <input type="checkbox" checked={primary} onChange={(e) => setPrimary(e.target.checked)} /> Primary sources
        </label>
        <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <input type="checkbox" checked={crossValidate} onChange={(e) => setCrossValidate(e.target.checked)} /> Cross-validate
        </label>
        <button
          onClick={submit}
          disabled={busy || !question.trim()}
          className="ml-auto inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all cursor-pointer disabled:opacity-50"
          style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          Start
        </button>
      </div>
      <p className="mt-2 text-[9px] leading-relaxed text-muted-foreground/70">
        Runs in the background; progress appears here. Results are evidence-grounded, never fabricated.
      </p>
    </div>
  );
}

// ── Answer / progress ────────────────────────────────────────────────────────

function AnswerWidget({ state }: { state: ResearchScreenState }) {
  const run = state.detail?.run;
  const s = state.status;
  const stateName = s?.state ?? run?.state;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Run Status" hint={stateName ?? '—'} />
      {!run ? (
        <EmptyNote>Select a run to see its progress.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-3 overflow-y-auto scrollbar-hide">
          <p className="text-[11px] leading-relaxed text-foreground">{run.question}</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Metric label="Sources" value={s?.sourceCount ?? state.detail?.sources.length ?? 0} />
            <Metric label="Evidence" value={s?.evidenceCount ?? state.detail?.evidence.length ?? 0} />
            <Metric label="Claims" value={s?.claimCount ?? state.detail?.claims.length ?? 0} />
            <Metric label="Conflicts" value={s?.conflictCount ?? state.detail?.conflicts.length ?? 0} />
            <Metric
              label="Sub-questions"
              value={s?.questionsTotal ? `${s.questionsAnswered ?? 0}/${s.questionsTotal}` : '—'}
            />
            <Metric label="Stop reason" value={run.status ?? s?.stopReason ?? '—'} mono />
          </div>
          {!TERMINAL.has(stateName ?? '') && (
            <p className="flex items-center gap-1.5 text-[10px] text-sky-400">
              <Loader2 className="h-3 w-3 animate-spin" /> Running… this panel updates live.
            </p>
          )}
          {state.error && <p className="text-[10px] text-rose-400">{state.error}</p>}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-border/10 glass-card-subtle px-2.5 py-1.5">
      <p className="text-[8px] font-bold uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className={cn('truncate text-xs font-bold text-foreground', mono && 'font-mono text-[10px]')}>{value}</p>
    </div>
  );
}

// ── Evidence (claim → evidence → source) ─────────────────────────────────────

function EvidenceWidget({ state }: { state: ResearchScreenState }) {
  const evidence: ResearchEvidenceRow[] = state.detail?.evidence ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Evidence" hint={`${evidence.length}`} />
      {!state.selectedId ? (
        <EmptyNote>Select a run.</EmptyNote>
      ) : evidence.length === 0 ? (
        <EmptyNote>No evidence fetched yet.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {evidence.map((e) => (
            <div key={e.evidenceId} className="rounded-lg border border-border/10 glass-card-subtle px-2.5 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-[10px] text-primary">{e.sourceUrl ?? e.evidenceId}</span>
                {e.contentTrust && (
                  <span className="shrink-0 font-mono text-[8px] uppercase text-amber-400/80">{e.contentTrust}</span>
                )}
              </div>
              {e.structuredValue != null && (
                <p className="mt-0.5 font-mono text-[10px] text-foreground">
                  {e.structuredValue}
                  {e.unit ?? ''} {e.period ? `· ${e.period}` : ''}
                </p>
              )}
              {e.rawText && (
                <p className="mt-0.5 line-clamp-2 text-[9px] leading-relaxed text-muted-foreground">
                  {e.rawText.slice(0, 200)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Claims + conflicts ───────────────────────────────────────────────────────

function ClaimsWidget({ state }: { state: ResearchScreenState }) {
  const claims = state.detail?.claims ?? [];
  const citations = state.detail?.citations ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Claims & Citations" hint={`${claims.length} · ${citations.length}`} />
      {claims.length === 0 ? (
        <EmptyNote>No claims recorded.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {claims.map((c, i) => {
            const claim = c as Record<string, unknown>;
            const claimStatus = String(claim.status ?? '');
            return (
              <div key={String(claim.id ?? i)} className="rounded-lg border border-border/10 glass-card-subtle px-2.5 py-2">
                <p className="line-clamp-2 text-[10px] text-foreground">{String(claim.text ?? '')}</p>
                <p className={cn('mt-0.5 font-mono text-[9px] uppercase',
                  claimStatus === 'SUPPORTED' ? 'text-emerald-400'
                    : claimStatus === 'CONTRADICTED' ? 'text-rose-400' : 'text-muted-foreground')}>
                  {claimStatus}{claim.confidence != null ? ` · ${Math.round(Number(claim.confidence) * 100)}%` : ''}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ConflictsWidget({ state }: { state: ResearchScreenState }) {
  const conflicts = state.detail?.conflicts ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Conflicts" hint={`${conflicts.length}`} />
      {conflicts.length === 0 ? (
        <EmptyNote>No unresolved conflicts.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
          {conflicts.map((c, i) => {
            const conflict = c as Record<string, unknown>;
            return (
              <div key={String(conflict.id ?? i)} className="rounded-lg border border-border/10 glass-card-subtle px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px] text-foreground">{String(conflict.metric ?? 'metric')}</span>
                  <span className="font-mono text-[9px] uppercase text-amber-400/80">{String(conflict.status ?? '')}</span>
                </div>
                {conflict.period != null && <p className="mt-0.5 font-mono text-[9px] text-muted-foreground">{String(conflict.period)}</p>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Schedule (recurring research via the existing jobs engine) ───────────────

interface TemplateView { id: string; name: string; kind: string; cron: string | null; intervalSeconds: number | null; parameters: Array<{ key: string; label: string; example: string }>; }

function ScheduleWidget() {
  const [templates, setTemplates] = React.useState<TemplateView[]>([]);
  const [topic, setTopic] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    void import('@/lib/harness/clients/jobs-browser')
      .then((m) => m.listJobTemplates())
      .then((all) => {
        const research = all.filter((t) => ['deep-research-brief', 'competitor-watch', 'research-topic-digest'].includes(t.id));
        setTemplates(research as unknown as TemplateView[]);
      })
      .catch(() => setTemplates([]))
      .finally(() => setLoaded(true));
  }, []);

  const enable = React.useCallback(async (template: TemplateView) => {
    const value = topic.trim();
    if (!value || busy) return;
    setBusy(true);
    setMessage(null);
    try {
      const m = await import('@/lib/harness/clients/jobs-browser');
      const key = template.parameters[0]?.key ?? 'topic';
      const { job } = await m.createJob({ templateId: template.id, params: { [key]: value } });
      await m.setJobEnabled(job.id, true);
      setMessage(`“${template.name}” enabled — it will run on its schedule.`);
      setTopic('');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Could not enable the schedule');
    } finally {
      setBusy(false);
    }
  }, [topic, busy]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Scheduled Research" hint="ONE-CLICK" />
      {!loaded ? (
        <EmptyNote>Loading templates…</EmptyNote>
      ) : templates.length === 0 ? (
        <EmptyNote>The scheduled-research templates are unavailable (runtime offline?).</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto scrollbar-hide">
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Topic or company to track"
            className="h-8 w-full rounded-lg border border-border/30 bg-transparent px-3 text-[11px] text-foreground placeholder:text-muted-foreground focus:border-primary/40 focus:outline-none"
          />
          {templates.map((t) => (
            <div key={t.id} className="flex items-center justify-between gap-2 rounded-lg border border-border/10 glass-card-subtle px-2.5 py-2">
              <div className="min-w-0">
                <p className="truncate text-[11px] text-foreground">{t.name}</p>
                <p className="font-mono text-[9px] text-muted-foreground">
                  {t.kind === 'cron' ? t.cron : `every ${Math.round((t.intervalSeconds ?? 0) / 3600)}h`}
                </p>
              </div>
              <button
                onClick={() => enable(t)}
                disabled={busy || !topic.trim()}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-primary/40 px-2 py-1 text-[10px] text-primary transition-colors cursor-pointer disabled:opacity-40"
              >
                <Zap className="h-3 w-3" /> Enable
              </button>
            </div>
          ))}
          {message && <p className="text-[10px] text-muted-foreground">{message}</p>}
          <p className="text-[9px] leading-relaxed text-muted-foreground/70">
            Enabling activates the existing scheduler; nothing runs until you enable it.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Entity / knowledge graph ─────────────────────────────────────────────────

function GraphWidget({ state }: { state: ResearchScreenState }) {
  const entities = state.detail?.entities ?? [];
  const relations = state.detail?.relations ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Knowledge Graph" hint={`${entities.length} · ${relations.length}`} />
      {entities.length === 0 ? (
        <EmptyNote>No entities extracted — every node is anchored to evidence, so none exist yet.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto scrollbar-hide">
          <div className="flex flex-wrap gap-1.5">
            {entities.slice(0, 40).map((e, i) => {
              const ent = e as Record<string, unknown>;
              return (
                <span
                  key={String(ent.entityId ?? i)}
                  className={cn(
                    'rounded-full border px-2 py-0.5 text-[10px]',
                    String(ent.kind) === 'company'
                      ? 'border-primary/40 bg-primary/10 text-primary'
                      : 'border-border/20 text-muted-foreground',
                  )}
                  title={String(ent.sourceUrl ?? '')}
                >
                  {String(ent.name ?? '')}
                </span>
              );
            })}
          </div>
          {relations.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Relations</p>
              {relations.slice(0, 30).map((r, i) => {
                const rel = r as Record<string, unknown>;
                return (
                  <p key={String(rel.id ?? i)} className="truncate font-mono text-[9px] text-muted-foreground">
                    {String(rel.subjectId ?? '')} — {String(rel.predicate ?? '')} →{' '}
                    {String(rel.objectValue ?? rel.objectId ?? '')}
                    {rel.unit ? String(rel.unit) : ''}
                  </p>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Registry ─────────────────────────────────────────────────────────────────

export const RESEARCH_WIDGETS: WidgetDefinition[] = [
  { id: 'research-runs', category: 'research', label: 'Research Runs', desc: 'All runs, newest first; select one to inspect.', icon: 'Database', sizes: ['medium', 'large'], defaultHeight: RESEARCH_FRAME_HEIGHT['research-runs'] },
  { id: 'research-run-form', category: 'research', label: 'New Research', desc: 'Start a background evidence-driven research run.', icon: 'Zap', sizes: ['medium', 'large'], minHeight: RESEARCH_MIN_HEIGHT['research-run-form'] },
  { id: 'research-answer', category: 'research', label: 'Run Status', desc: 'Live progress and counts for the selected run.', icon: 'Activity', sizes: ['medium', 'large'], minHeight: RESEARCH_MIN_HEIGHT['research-answer'] },
  { id: 'research-evidence', category: 'research', label: 'Evidence', desc: 'Fetched evidence with provenance and trust.', icon: 'FileText', sizes: ['medium', 'large', 'full'], defaultHeight: RESEARCH_FRAME_HEIGHT['research-evidence'] },
  { id: 'research-claims', category: 'research', label: 'Claims & Citations', desc: 'Verified claims with their citations.', icon: 'Check', sizes: ['medium', 'large'], defaultHeight: RESEARCH_FRAME_HEIGHT['research-claims'] },
  { id: 'research-conflicts', category: 'research', label: 'Conflicts', desc: 'Unresolved / explained source conflicts.', icon: 'Activity', sizes: ['small', 'medium'], defaultHeight: RESEARCH_FRAME_HEIGHT['research-conflicts'] },
  { id: 'research-schedule', category: 'research', label: 'Scheduled Research', desc: 'Enable a recurring research brief in one click.', icon: 'RefreshCw', sizes: ['medium', 'large'], minHeight: RESEARCH_MIN_HEIGHT['research-schedule'] },
  { id: 'research-graph', category: 'research', label: 'Knowledge Graph', desc: 'Evidence-anchored entities and relations a run extracted.', icon: 'Globe2', sizes: ['medium', 'large', 'full'], minHeight: RESEARCH_MIN_HEIGHT['research-graph'] },
];

export const RESEARCH_WIDGET_IDS = RESEARCH_WIDGETS.map((w) => w.id);

export function researchWidgetIcon(_name: string): React.ComponentType<{ size?: number; className?: string }> {
  return Database;
}

export function renderResearchWidget(widgetId: string, state: ResearchScreenState): React.ReactNode {
  switch (widgetId) {
    case 'research-runs': return <RunsWidget state={state} />;
    case 'research-run-form': return <StartFormWidget state={state} />;
    case 'research-answer': return <AnswerWidget state={state} />;
    case 'research-evidence': return <EvidenceWidget state={state} />;
    case 'research-claims': return <ClaimsWidget state={state} />;
    case 'research-conflicts': return <ConflictsWidget state={state} />;
    case 'research-schedule': return <ScheduleWidget />;
    case 'research-graph': return <GraphWidget state={state} />;
    default: return <EmptyNote>Unknown widget “{widgetId}”.</EmptyNote>;
  }
}
