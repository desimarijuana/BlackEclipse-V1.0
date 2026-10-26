'use client';

// ── Graph Studio home ────────────────────────────────────────────────────────
// The n8n-style "workflows" landing surface: a searchable gallery of saved
// workflows plus the template starter set and the prompt-to-graph entry point.
// Opening a workflow switches the workspace into the full-bleed editor.

import { useEffect, useMemo, useState } from 'react';
import {
  ArrowRight, ChevronDown, Clock, GitBranch, Home, Plus, Search, Sparkles, Trash2,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { useWorkflowCatalog } from '@/lib/graph-studio/catalog-store';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { WORKFLOW_TEMPLATES } from '@/lib/graph-studio/templates';
import { planGraph } from '@/lib/graph-studio/plan-client';

function relativeDate(value: string): string {
  const then = new Date(value).getTime();
  if (!Number.isFinite(then)) return '';
  const delta = Date.now() - then;
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
}

export function GraphHome({
  onOpen,
  onExit,
  eyebrow = 'Graph Studio',
  title = 'Workflows',
  subtitle = 'Build, validate and run typed workflows. Every graph compiles to the same workflow model.',
  showExit = true,
}: {
  onOpen: () => void;
  onExit?: () => void;
  eyebrow?: string;
  title?: string;
  subtitle?: string;
  showExit?: boolean;
}) {
  const summaries = useWorkflowCatalog((s) => s.summaries);
  const loading = useWorkflowCatalog((s) => s.loading);
  const busy = useWorkflowCatalog((s) => s.busy);
  const error = useWorkflowCatalog((s) => s.error);
  const refresh = useWorkflowCatalog((s) => s.refresh);
  const open = useWorkflowCatalog((s) => s.open);
  const createFromTemplate = useWorkflowCatalog((s) => s.createFromTemplate);
  const createFromIr = useWorkflowCatalog((s) => s.createFromIr);
  const remove = useWorkflowCatalog((s) => s.remove);
  const activeId = useGraphEditor((s) => s.workflowId);
  const activeName = useGraphEditor((s) => s.ir?.name);
  const activeDirty = useGraphEditor((s) => s.dirty);

  const [query, setQuery] = useState('');
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [objective, setObjective] = useState('');
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return summaries;
    return summaries.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.tags.some((tag) => tag.toLowerCase().includes(q)),
    );
  }, [summaries, query]);

  const confirmDiscard = () => !useGraphEditor.getState().dirty || window.confirm('Discard the unsaved changes in the current workflow?');

  const beginFromTemplate = async (templateId: string) => {
    if (!confirmDiscard()) return;
    setTemplatesOpen(false);
    await createFromTemplate(templateId);
    if (!useWorkflowCatalog.getState().error) onOpen();
  };

  const plan = async () => {
    if (!confirmDiscard()) return;
    setPlanning(true);
    setPlanError(null);
    try {
      const result = await planGraph(objective.trim());
      if (!result.ok || !result.ir) {
        setPlanError(result.errors.map((item) => item.message).join('; ') || 'The model did not return a usable graph.');
        return;
      }
      await createFromIr(
        result.ir.name || 'Generated workflow',
        result.ir.description || `Generated from: ${objective.trim()}`,
        result.ir,
      );
      setGenerateOpen(false);
      setObjective('');
      onOpen();
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : 'Graph planning failed');
    } finally {
      setPlanning(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="w-full px-4 py-6 md:px-6 lg:px-8">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-sky-400">
              <GitBranch size={14} /> {eyebrow}
            </div>
            <h1 className="mt-1 text-[24px] font-semibold tracking-tight text-foreground">{title}</h1>
            <p className="mt-1 max-w-xl text-[12px] text-muted-foreground">{subtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            {showExit && onExit && (
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                onClick={onExit}
                title="Back to Eclipse"
              >
                <Home size={14} />
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || planning}
              onClick={() => {
                setGenerateOpen((value) => !value);
                setPlanError(null);
              }}
            >
              <Sparkles size={13} /> Generate from prompt
            </Button>
            <div className="relative">
              <Button
                type="button"
                size="sm"
                disabled={busy}
                onClick={() => setTemplatesOpen((value) => !value)}
              >
                <Plus size={13} /> New workflow <ChevronDown size={11} />
              </Button>
              {templatesOpen && (
                <div className="glass-tooltip absolute right-0 top-10 z-30 w-[300px] rounded-xl border border-white/10 p-1.5">
                  {WORKFLOW_TEMPLATES.map((template) => (
                    <button
                      key={template.id}
                      type="button"
                      onClick={() => void beginFromTemplate(template.id)}
                      className="block w-full rounded-lg px-2.5 py-2 text-left hover:bg-white/5"
                    >
                      <span className="block text-[12px] font-medium text-foreground">{template.name}</span>
                      <span className="mt-0.5 block text-[10.5px] leading-snug text-muted-foreground">{template.description}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </header>

        {generateOpen && (
          <div className="glass-card mt-4 rounded-xl border border-white/10 p-3">
            <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-foreground">
              <Sparkles size={13} className="text-sky-400" /> Describe the workflow
            </div>
            <textarea
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              rows={3}
              placeholder="Fetch AAPL daily bars, compute an SMA z-score, branch on the signal and report the result."
              className="w-full resize-none rounded-lg border border-white/10 bg-background/60 px-2.5 py-2 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-sky-400/50"
            />
            <div className="mt-2 flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                disabled={planning || objective.trim().length < 8}
                onClick={() => void plan()}
              >
                {planning ? 'Generating…' : 'Generate graph'}
              </Button>
              <span className="text-[10px] text-muted-foreground">Nothing is saved until the plan validates.</span>
            </div>
            {planError && <p className="mt-2 rounded bg-rose-500/10 px-2 py-1.5 text-[10.5px] text-rose-200">{planError}</p>}
          </div>
        )}

        <div className="mt-6 flex items-center gap-2">
          <div className="relative min-w-0 flex-1 sm:max-w-sm">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search workflows…"
              className="w-full rounded-lg border border-white/10 bg-background/60 py-1.5 pl-8 pr-2 text-[12px] outline-none focus:border-sky-400/50"
            />
          </div>
          <span className="ml-auto text-[10.5px] text-muted-foreground">{filtered.length} workflow{filtered.length === 1 ? '' : 's'}</span>
        </div>

        {error && <p className="mt-3 rounded-md bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-200">{error}</p>}

        {activeId && activeName && (
          <button
            type="button"
            onClick={onOpen}
            className="mt-4 flex w-full items-center gap-3 rounded-xl border border-sky-400/25 bg-sky-500/[0.06] px-3 py-2.5 text-left transition-colors hover:border-sky-400/40 hover:bg-sky-500/10"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sky-500/15 text-sky-300">
              <GitBranch size={15} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12.5px] font-medium text-foreground">Continue editing {activeName}</span>
              <span className="block text-[10.5px] text-muted-foreground">
                {activeDirty ? 'Unsaved changes are still in the editor.' : 'Reopen the editor where you left off.'}
              </span>
            </span>
            <ArrowRight size={13} className="shrink-0 text-sky-300" />
          </button>
        )}

        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {loading && summaries.length === 0 && (
            <p className="col-span-full py-10 text-center text-[12px] text-muted-foreground">Loading workflows…</p>
          )}
          {!loading && filtered.length === 0 && (
            <div className="glass-card col-span-full flex flex-col items-center gap-2 rounded-xl border border-dashed border-white/15 px-6 py-12 text-center">
              <GitBranch size={24} className="text-sky-400/80" />
              <p className="text-[13px] font-medium text-foreground">
                {summaries.length === 0 ? 'No workflows yet' : 'No workflows match that search'}
              </p>
              <p className="max-w-sm text-[11.5px] text-muted-foreground">
                {summaries.length === 0
                  ? 'Start from a template or describe the workflow you want.'
                  : 'Try a different name, description or tag.'}
              </p>
              {summaries.length === 0 && (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => setTemplatesOpen(true)}
                  className="mt-1"
                >
                  <Plus size={13} /> New workflow
                </Button>
              )}
            </div>
          )}
          {filtered.map((summary) => (
            <article
              key={summary.id}
              className="glass-card group relative flex min-h-[112px] flex-col rounded-xl border border-white/10 p-3 transition-colors hover:border-sky-400/30"
            >
              <button
                type="button"
                onClick={() => {
                  if (!confirmDiscard()) return;
                  void open(summary.id).then(() => {
                    if (!useWorkflowCatalog.getState().error) onOpen();
                  });
                }}
                className="min-w-0 flex-1 text-left"
              >
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-sky-500/10 text-sky-300">
                    <GitBranch size={14} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-foreground">{summary.name}</span>
                    <span className="mt-0.5 line-clamp-2 block text-[10.5px] leading-snug text-muted-foreground">
                      {summary.description || 'No description.'}
                    </span>
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[9.5px] text-muted-foreground">
                  <span className="rounded-full border border-white/10 px-1.5 py-0.5">v{summary.currentVersion}</span>
                  <span className="flex items-center gap-1"><Clock size={9} /> {relativeDate(summary.updatedAt)}</span>
                  {summary.tags.slice(0, 2).map((tag) => (
                    <span key={tag} className="rounded-full bg-white/5 px-1.5 py-0.5">{tag}</span>
                  ))}
                </div>
              </button>
              <div className="mt-2 flex items-center justify-between border-t border-white/5 pt-1.5">
                <span className="flex items-center gap-1 text-[10px] font-medium text-sky-300 opacity-0 transition-opacity group-hover:opacity-100">
                  Open editor <ArrowRight size={10} />
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  title="Delete workflow"
                  onClick={() => {
                    if (window.confirm(`Delete “${summary.name}”? This removes its saved versions.`)) void remove(summary.id);
                  }}
                  className="text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-rose-400"
                >
                  <Trash2 size={11} />
                </Button>
              </div>
            </article>
          ))}
        </div>

        <section className="mt-8">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Start from a template</h2>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {WORKFLOW_TEMPLATES.map((template) => (
              <button
                key={template.id}
                type="button"
                disabled={busy}
                onClick={() => void beginFromTemplate(template.id)}
                className="glass-card-subtle rounded-xl border border-white/10 p-3 text-left transition-colors hover:border-sky-400/30 hover:bg-white/[0.04] disabled:opacity-50"
              >
                <span className="block text-[12px] font-medium text-foreground">{template.name}</span>
                <span className="mt-0.5 block text-[10.5px] leading-snug text-muted-foreground">{template.description}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
