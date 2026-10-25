'use client';

// ── Workflow list ────────────────────────────────────────────────────────────
// The mode panel's workflow browser: open / create-from-template / delete.
// All state comes from the shared catalog store, so the workspace screen and
// this panel can never disagree about what exists.

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { Plus, Trash2 } from '@/lib/icons';
import { useWorkflowCatalog } from '@/lib/graph-studio/catalog-store';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { WORKFLOW_TEMPLATES } from '@/lib/graph-studio/templates';
import { planGraph } from '@/lib/graph-studio/plan-client';

export function WorkflowList({ onOpened }: { onOpened?: () => void } = {}) {
  const summaries = useWorkflowCatalog((s) => s.summaries);
  const busy = useWorkflowCatalog((s) => s.busy);
  const loading = useWorkflowCatalog((s) => s.loading);
  const error = useWorkflowCatalog((s) => s.error);
  const refresh = useWorkflowCatalog((s) => s.refresh);
  const open = useWorkflowCatalog((s) => s.open);
  const createFromTemplate = useWorkflowCatalog((s) => s.createFromTemplate);
  const createFromIr = useWorkflowCatalog((s) => s.createFromIr);
  const remove = useWorkflowCatalog((s) => s.remove);
  const activeId = useGraphEditor((s) => s.workflowId);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [objective, setObjective] = useState('');
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative mb-2 shrink-0">
        <button
          type="button"
          disabled={busy}
          onClick={() => setTemplatesOpen((v) => !v)}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-sky-400/30 bg-sky-500/10 px-2 py-1.5 text-[11px] text-sky-200 hover:bg-sky-500/20 disabled:opacity-50"
        >
          <Plus size={13} /> New workflow
        </button>
        {templatesOpen && (
          <div className="glass-card-strong absolute left-0 right-0 top-9 z-30 rounded-lg border border-white/10 p-1.5">
            {WORKFLOW_TEMPLATES.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => {
                  setTemplatesOpen(false);
                  void createFromTemplate(template.id).then(() => onOpened?.());
                }}
                className="block w-full rounded-md px-2 py-1.5 text-left hover:bg-white/5"
              >
                <span className="block text-[12px] text-foreground">{template.name}</span>
                <span className="block text-[10px] text-muted-foreground">{template.description}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="mb-2 shrink-0">
        <button
          type="button"
          disabled={busy || planning}
          onClick={() => {
            setGenerateOpen((value) => !value);
            setPlanError(null);
          }}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-white/10 px-2 py-1.5 text-[11px] text-muted-foreground hover:bg-white/5 hover:text-foreground disabled:opacity-50"
        >
          <Plus size={13} /> Generate from prompt
        </button>
        {generateOpen && (
          <div className="mt-1.5 rounded-lg border border-white/10 bg-white/[0.02] p-2">
            <textarea
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              rows={3}
              placeholder="Describe the workflow, e.g. fetch AAPL daily bars, compute an SMA z-score, branch on the signal and report the result."
              className="w-full resize-none rounded-md border border-white/10 bg-transparent px-2 py-1.5 text-[11px] text-foreground placeholder:text-muted-foreground/60"
            />
            <div className="mt-1.5 flex items-center gap-1.5">
              <button
                type="button"
                disabled={planning || objective.trim().length < 8}
                onClick={() => {
                  void (async () => {
                    setPlanning(true);
                    setPlanError(null);
                    try {
                      const result = await planGraph(objective.trim());
                      if (!result.ok || !result.ir) {
                        setPlanError(
                          result.errors.map((item) => item.message).join('; ') ||
                            'The model did not return a usable graph.',
                        );
                        return;
                      }
                      await createFromIr(
                        result.ir.name || 'Generated workflow',
                        result.ir.description || `Generated from: ${objective.trim()}`,
                        result.ir,
                      );
                      setGenerateOpen(false);
                      setObjective('');
                      onOpened?.();
                    } catch (err) {
                      setPlanError(err instanceof Error ? err.message : 'Graph planning failed');
                    } finally {
                      setPlanning(false);
                    }
                  })();
                }}
                className="rounded-md border border-sky-400/30 bg-sky-500/10 px-2 py-1 text-[10.5px] text-sky-200 hover:bg-sky-500/20 disabled:opacity-40"
              >
                {planning ? 'Generating…' : 'Generate graph'}
              </button>
              <span className="text-[9.5px] text-muted-foreground">
                Nothing is saved until the plan validates.
              </span>
            </div>
            {planError && (
              <p className="mt-1.5 rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-200">{planError}</p>
            )}
          </div>
        )}
      </div>

      {error && <p className="mb-2 shrink-0 rounded-md bg-rose-500/10 px-2 py-1 text-[10.5px] text-rose-200">{error}</p>}

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
        {loading && summaries.length === 0 && (
          <p className="px-1 py-3 text-[11px] text-muted-foreground">Loading…</p>
        )}
        {!loading && summaries.length === 0 && (
          <p className="px-1 py-3 text-[11px] text-muted-foreground">
            No workflows yet — create one from a template.
          </p>
        )}
        {summaries.map((summary) => (
          <div
            key={summary.id}
            className={cn(
              'group flex items-center gap-1 rounded-lg border px-2 py-1.5',
              activeId === summary.id ? 'border-sky-400/40 bg-sky-500/10' : 'border-white/10 hover:bg-white/5',
            )}
          >
            <button
              type="button"
              onClick={() => void open(summary.id).then(() => onOpened?.())}
              className="min-w-0 flex-1 text-left"
            >
              <span className="block truncate text-[12px] text-foreground">{summary.name}</span>
              <span className="block text-[10px] text-muted-foreground">
                v{summary.currentVersion} · {new Date(summary.updatedAt).toLocaleDateString()}
              </span>
            </button>
            <button
              type="button"
              onClick={() => void remove(summary.id)}
              title="Delete workflow"
              className="shrink-0 rounded p-1 text-muted-foreground opacity-0 hover:text-rose-400 group-hover:opacity-100"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
