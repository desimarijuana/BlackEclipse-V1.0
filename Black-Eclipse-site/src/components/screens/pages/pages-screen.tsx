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
import { Lock, Plus, RefreshCw, RotateCcw, Save } from '@/lib/icons';
import { DASHBOARD_WIDGET_IDS, widgetIcon, renderDashboardWidget } from '@/lib/dashboard/registry';
import { useWidgets } from '@/lib/workspace/use-widgets';
import { CustomizableWorkspace } from '@/components/workspace';
import { loadWorkspace, clearWorkspace } from '@/lib/workspace/persistence';
import {
  createPage,
  getCurrentPage,
  listBlueprints,
  resolveCurrentPage,
  saveLayout,
  type BlueprintSummary,
  type UiBlueprint,
} from '@/lib/harness/clients/ui-client';
import {
  blueprintLayoutToKernel,
  isDashboardMirrorPath,
  kernelLayoutToWire,
  pageStorageKey,
} from '@/lib/ui-engineering/live-page';
import { setUiFocus } from '@/lib/ui-engineering/ui-focus';
import { isSetupOverlayOpen, subscribeSetupOverlay } from '@/lib/setup/overlay';
import { eclipseSdk } from '@/lib/sdk';

/** The page requested by `?tab=pages&page=<id|path>` (SDK/sidebar deep link). */
function requestedPage(): string | null {
  if (typeof window === 'undefined') return null;
  const sp = new URLSearchParams(window.location.search);
  return sp.get('tab') === 'pages' ? sp.get('page') : null;
}

/** Reflect the open page in the URL so it is shareable and back/forward works. */
function rememberPage(blueprintId: string) {
  if (typeof window === 'undefined') return;
  const sp = new URLSearchParams(window.location.search);
  sp.set('tab', 'pages');
  sp.set('page', blueprintId);
  window.history.replaceState(null, '', `/?${sp.toString()}`);
}

export function PagesScreen() {
  const [blueprints, setBlueprints] = useState<BlueprintSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [blueprint, setBlueprint] = useState<UiBlueprint | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  // Bumped to force the workspace to remount (re-seed from the blueprint).
  const [remount, setRemount] = useState(0);
  const [pageLocked, setPageLocked] = useState(false);
  const allWidgets = useWidgets({ surface: 'page' });

  // Surface a page lock outside the SDK tab.
  const refreshPageLock = useCallback(async () => {
    if (!selectedId) {
      setPageLocked(false);
      return;
    }
    try {
      const { locks } = await eclipseSdk.locks.list({ resourceType: 'page', resourceId: selectedId });
      setPageLocked(locks.length > 0);
    } catch {
      setPageLocked(false);
    }
  }, [selectedId]);
  useEffect(() => {
    void refreshPageLock();
    const onChanged = () => void refreshPageLock();
    window.addEventListener('eclipse:locks-changed', onChanged);
    const timer = window.setInterval(() => void refreshPageLock(), 30_000);
    return () => {
      window.removeEventListener('eclipse:locks-changed', onChanged);
      window.clearInterval(timer);
    };
  }, [refreshPageLock]);

  const refreshList = useCallback(async () => {
    try {
      const { blueprints: list } = await listBlueprints({ limit: 100 });
      const visible = list.filter((b) => !isDashboardMirrorPath(b.path));
      setBlueprints(visible);
      setError(null);
      return visible;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'runtime unavailable');
      return [];
    }
  }, []);

  const openPage = useCallback(async (idOrPath: string) => {
    setBusy(true);
    try {
      let bp: UiBlueprint;
      if (/^uibp[_-]/.test(idOrPath)) {
        bp = (await getCurrentPage(idOrPath)).blueprint;
      } else {
        // A path (or an id from an older SDK) resolves through the runtime's
        // path lookup; fall back to id lookup so both forms work.
        try {
          bp = (await resolveCurrentPage({ path: idOrPath })).blueprint;
        } catch {
          bp = (await getCurrentPage(idOrPath)).blueprint;
        }
      }
      setSelectedId(bp.id);
      setBlueprint(bp);
      rememberPage(bp.id);
      // Tell the chat which page the user is working on.
      setUiFocus({ page: { blueprintId: bp.id, title: bp.title, path: bp.path ?? undefined } });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to open page');
    } finally {
      setBusy(false);
    }
  }, []);

  // SDK/sidebar deep links: open the requested page on mount and whenever the
  // shell navigates to another `?tab=pages&page=…` entry (popstate).
  useEffect(() => {
    const onPop = () => {
      const wanted = requestedPage();
      if (wanted) void openPage(wanted);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [openPage]);

  useEffect(() => {
    void (async () => {
      const list = await refreshList();
      const wanted = requestedPage();
      const target = wanted
        ? (list.find((b) => b.id === wanted || b.path === wanted)?.id ?? wanted)
        : list[0]?.id;
      if (target && (wanted || !selectedId)) await openPage(target);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open the first page once on mount
  }, [refreshList, openPage]);

  // Live refresh: the runtime pushes a `changed` event over SSE
  // (`/api/ui/stream`) when a blueprint's revision moves; we then re-list and
  // reload the open page ONLY if its durable revision actually changed — a
  // no-op otherwise, so a user's unsaved local arrangement is never yanked.
  // Window focus is a fallback; a slow poll covers a dropped stream.
  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const { blueprints: list } = await listBlueprints({ limit: 100 });
        if (cancelled) return;
        setBlueprints(list.filter((b) => !isDashboardMirrorPath(b.path)));
        const current = list.find((b) => b.id === selectedId);
        if (current && (!blueprint || current.revision !== blueprint.revision)) {
          await openPage(selectedId!);
        }
      } catch {
        /* best-effort: keep the current view */
      }
    };
    window.addEventListener('focus', check);

    let source: EventSource | null = null;
    let fallback: ReturnType<typeof setInterval> | null = null;
    const startFallback = () => {
      if (!fallback) fallback = setInterval(() => void check(), 60_000);
    };
    // Closed while the setup wizard is overlaid so it cannot hold one of the
    // browser's six per-origin connections against the wizard's save.
    const connect = () => {
      if (source || isSetupOverlayOpen()) return;
      try {
        source = new EventSource('/api/ui/stream');
        source.addEventListener('changed', () => void check());
        source.addEventListener('error', () => {
          // Browser will auto-reconnect; add a poll as a safety net meanwhile.
          startFallback();
        });
      } catch {
        source = null;
        startFallback();
      }
    };
    const disconnect = () => {
      source?.close();
      source = null;
    };
    connect();
    const unsubscribeOverlay = subscribeSetupOverlay((open) => {
      if (open) {
        disconnect();
        if (fallback) {
          clearInterval(fallback);
          fallback = null;
        }
      } else {
        connect();
        void check();
      }
    });

    return () => {
      cancelled = true;
      window.removeEventListener('focus', check);
      unsubscribeOverlay();
      disconnect();
      if (fallback) clearInterval(fallback);
    };
  }, [selectedId, blueprint, openPage]);

  const defaultLayout = useMemo(
    () => blueprintLayoutToKernel(blueprint?.layout),
    [blueprint],
  );

  // Keep every id present in the blueprint — including ones the host registry
  // does not render yet (an agent-added or engineered widget) — so the kernel
  // does not silently drop it. Unknown ids render a visible placeholder.
  const knownWidgetIds = useMemo(() => {
    const ids = new Set<string>([...DASHBOARD_WIDGET_IDS, ...allWidgets.map((w) => w.id)]);
    for (const section of blueprint?.layout.sections ?? []) {
      for (const column of section.columns ?? []) {
        for (const widget of column.widgets ?? []) ids.add(widget.widgetId);
      }
    }
    return [...ids];
  }, [blueprint, allWidgets]);

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
      const { layout } = loadWorkspace(pageStorageKey(selectedId, blueprint.revision), defaultLayout);
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
    clearWorkspace(pageStorageKey(selectedId, blueprint?.revision));
    setNote('Reverted to the page’s saved arrangement');
    // Force the workspace to remount and re-seed from the blueprint.
    setRemount((n) => n + 1);
  };

  // Refresh re-lists pages AND reloads the open one, so an edit the agent just
  // made to the blueprint shows up without reopening the page.
  const handleRefresh = async () => {
    const list = await refreshList();
    const target = selectedId && list.some((b) => b.id === selectedId) ? selectedId : list[0]?.id;
    if (target) await openPage(target);
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-semibold text-foreground">Pages</h1>
          <p className="text-xs text-muted-foreground">
            Custom pages you and Eclipse compose. Add or rearrange widgets like the Command Center, then save the arrangement to the page.
          </p>
          {pageLocked && (
            <span className="mt-1 inline-flex items-center gap-1 rounded border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide text-amber-300">
              <Lock size={9} /> Locked
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => void handleRefresh()} className="glass-button inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-foreground">
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
            {blueprints.map((b) => {
              const PageIcon = widgetIcon(b.icon ?? 'dashboard');
              return (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => void openPage(b.id)}
                  className={cn(
                    'w-full rounded-lg px-2.5 py-2 text-left text-xs transition-colors',
                    selectedId === b.id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:bg-white/5',
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    <PageIcon size={12} className="shrink-0 text-primary/80" />
                    <span className="truncate font-medium text-foreground">{b.title}</span>
                  </span>
                  <span className="text-[10px] text-muted-foreground">{b.kind} · r{b.revision} · {b.widgetCount} widgets</span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="glass-card flex min-h-0 flex-col rounded-xl p-4">
          {!blueprint && <p className="text-xs text-muted-foreground">Select or create a page to begin.</p>}
          {blueprint && (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="flex items-center gap-2 text-sm font-medium text-foreground">
                  {(() => { const HIcon = widgetIcon(blueprint.icon ?? 'dashboard'); return <HIcon size={15} className="text-primary" />; })()}
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
                  storageKey={pageStorageKey(blueprint.id, blueprint.revision)}
                  defaultLayout={defaultLayout}
                  widgets={allWidgets}
                  knownWidgetIds={knownWidgetIds}
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
