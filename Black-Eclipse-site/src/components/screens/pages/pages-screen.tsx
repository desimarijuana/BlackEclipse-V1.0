'use client';

// ── Pages — the live surface for agent/user authored pages ───────────────────
// Lists the saved UI blueprints and renders the selected one through the REAL
// workspace kernel (`CustomizableWorkspace`) + the real widget registry
// (`renderDashboardWidget`), so a page the agent composes is an actual, usable
// page — not a disconnected blueprint in a separate store.
//
// This is the bridge between the UI-Engineering runtime (blueprints on
// agent-memory.db) and the live app. The user may rearrange a page locally; the
// "Save to page" action writes that arrangement back to the blueprint as a new
// revision (`ui_save_layout`), and "Revert to page" discards the local cache.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Plus, RefreshCw, RotateCcw, Save } from '@/lib/icons';
import { DASHBOARD_WIDGETS, widgetIcon, renderDashboardWidget } from '@/lib/dashboard/registry';
import { CustomizableWorkspace } from '@/components/workspace';
import { loadWorkspace, clearWorkspace } from '@/lib/workspace/persistence';
import {
  createPage,
  getCurrentPage,
  listBlueprints,
  saveLayout,
  type BlueprintSummary,
  type UiBlueprint,
} from '@/lib/harness/ui-client';
import {
  blueprintLayoutToKernel,
  kernelLayoutToWire,
  pageStorageKey,
} from '@/lib/ui-engineering/live-page';
import { setUiFocus } from '@/lib/ui-engineering/ui-focus';

export function PagesScreen() {
  const [blueprints, setBlueprints] = useState<BlueprintSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [blueprint, setBlueprint] = useState<UiBlueprint | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  // Bumped to force the workspace to remount (re-seed from the blueprint).
  const [remount, setRemount] = useState(0);

  const refreshList = useCallback(async () => {
    try {
      const { blueprints: list } = await listBlueprints({ limit: 100 });
      setBlueprints(list);
      setError(null);
      return list;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'runtime unavailable');
      return [];
    }
  }, []);

  const openPage = useCallback(async (id: string) => {
    setBusy(true);
    try {
      const { blueprint: bp } = await getCurrentPage(id);
      setSelectedId(id);
      setBlueprint(bp);
      // Tell the chat which page the user is working on.
      setUiFocus({ page: { blueprintId: bp.id, title: bp.title, path: bp.path ?? undefined } });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to open page');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const list = await refreshList();
      if (list.length && !selectedId) await openPage(list[0].id);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open the first page once on mount
  }, [refreshList, openPage]);

  const defaultLayout = useMemo(
    () => blueprintLayoutToKernel(blueprint?.layout),
    [blueprint],
  );

  const handleCreate = async () => {
    setBusy(true);
    try {
      const { blueprint: created } = await createPage({ title: `Untitled page ${blueprints.length + 1}` });
      await refreshList();
      await openPage(created.id);
      setNote(`Created “${created.title}”`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'create failed');
    } finally {
      setBusy(false);
    }
  };

  // Write the user's local arrangement back to the durable blueprint.
  const handleSaveToPage = async () => {
    if (!selectedId || !blueprint) return;
    setBusy(true);
    try {
      const { layout } = loadWorkspace(pageStorageKey(selectedId), defaultLayout);
      const { blueprint: saved } = await saveLayout(selectedId, kernelLayoutToWire(layout), blueprint.revision);
      setBlueprint(saved);
      setNote(`Saved arrangement to “${saved.title}” (r${saved.revision})`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setBusy(false);
    }
  };

  // Discard the local cache and re-seed from the blueprint.
  const handleRevert = () => {
    if (!selectedId) return;
    clearWorkspace(pageStorageKey(selectedId));
    setNote('Reverted to the page’s saved arrangement');
    // Force the workspace to remount and re-seed from the blueprint.
    setRemount((n) => n + 1);
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-semibold text-foreground">Pages</h1>
          <p className="text-xs text-muted-foreground">
            Custom pages you and Eclipse compose. Add or rearrange widgets like the Command Center, then save the arrangement to the page.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => void refreshList()} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-foreground">
            <RefreshCw size={13} /> Refresh
          </button>
          <button type="button" onClick={() => void handleCreate()} disabled={busy} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-foreground disabled:opacity-50">
            <Plus size={14} /> New page
          </button>
        </div>
      </header>

      {error && <div className="glass-card-subtle rounded-lg px-3 py-2 text-xs text-rose-300">Runtime: {error}</div>}
      {note && !error && <div className="glass-card-subtle rounded-lg px-3 py-2 text-xs text-emerald-300">{note}</div>}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="glass-card flex min-h-0 flex-col rounded-xl p-3">
          <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Your pages</h2>
          <div className="flex-1 space-y-1 overflow-y-auto">
            {blueprints.length === 0 && <p className="text-xs text-muted-foreground">No pages yet. Create one, or ask Eclipse to.</p>}
            {blueprints.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => void openPage(b.id)}
                className={cn(
                  'w-full rounded-lg px-2.5 py-2 text-left text-xs transition-colors',
                  selectedId === b.id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:bg-white/5',
                )}
              >
                <span className="block truncate font-medium text-foreground">{b.title}</span>
                <span className="text-[10px] text-muted-foreground">{b.kind} · r{b.revision} · {b.widgetCount} widgets</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="glass-card flex min-h-0 flex-col rounded-xl p-4">
          {!blueprint && <p className="text-xs text-muted-foreground">Select or create a page to begin.</p>}
          {blueprint && (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-medium text-foreground">
                  {blueprint.title} <span className="text-xs text-muted-foreground">(r{blueprint.revision})</span>
                </h2>
                <div className="flex items-center gap-2">
                  <button type="button" onClick={handleRevert} disabled={busy} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-foreground disabled:opacity-50">
                    <RotateCcw size={13} /> Revert
                  </button>
                  <button type="button" onClick={() => void handleSaveToPage()} disabled={busy} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-foreground disabled:opacity-50">
                    <Save size={13} /> Save to page
                  </button>
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">
                <CustomizableWorkspace
                  key={`${blueprint.id}:${blueprint.revision}:${blueprint.updatedAt}:${remount}`}
                  storageKey={pageStorageKey(blueprint.id)}
                  defaultLayout={defaultLayout}
                  widgets={DASHBOARD_WIDGETS}
                  widgetIcon={widgetIcon}
                  renderWidget={(widgetId, placement) => renderDashboardWidget(widgetId, placement)}
                  toolbar="icons"
                />
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
