'use client';

// ── CustomizableWorkspace — reusable customizable widget grid ────────────────
// The one-stop composite for any page that wants a drag-and-drop, click-to-place
// widget workspace. It wires together the workspace kernel (useWorkspace +
// WorkspaceCanvas) with the searchable WidgetLibrary and the per-instance
// WidgetConfigPanel, plus the edit-mode toggle and floating "Add Widget" button.
//
// A page only needs to supply: a storageKey, a default layout, its widget
// definitions, and a render function. Everything else (persistence, drag/drop,
// click-to-place, left/right buttons, duplicate, hide, config, library) is
// handled here.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Plus, RefreshCw, Settings2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePageShortcuts, useKeyboardShortcutsStore } from '@/hooks/use-page-shortcuts';
import { isKeyboardEventAvailable } from '@/lib/keyboard';
import { useWorkspace } from '@/lib/workspace/use-workspace';
import { WorkspaceCanvas } from '@/lib/workspace/workspace-canvas';
import { dataHub, useRefreshAll } from '@/lib/workspace/data-hub';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WidgetPlacement, WorkspaceLayout } from '@/lib/workspace/types';
import { WidgetConfigProvider } from '@/lib/workspace/widget-config-context';
import { WidgetLibrary } from './widget-library';
import { WidgetConfigPanel } from './widget-config';

export interface CustomizableWorkspaceProps {
  /** localStorage key — unique per page/instance. */
  storageKey: string;
  /** Default layout (used on first load / reset). */
  defaultLayout: WorkspaceLayout;
  /** Widget definitions for this page. */
  widgets: WidgetDefinition[];
  /** Resolve a widget's icon by name (lucide). */
  widgetIcon: (name: string) => React.ComponentType<{ size?: number; className?: string }>;
  /** Render a widget's content. */
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  /** Optional extra chrome rendered in the top-right of the edit bar. */
  editBarExtra?: React.ReactNode;
  /** Optional bottom status bar rendered under the canvas. */
  statusBar?: React.ReactNode;
  /** Toolbar style: full labelled buttons, icon-only (for narrow columns), or hidden. */
  toolbar?: 'default' | 'compact' | 'none';
  /** Hide the floating "Add Widget" button (e.g. in a narrow side panel). */
  hideFloatingAdd?: boolean;
  /** Width class for the secondary rail zone (sections with zone:'rail'). */
  railClassName?: string;
  /** Header rendered above the rail zone (e.g. the "Market" title + collapse). */
  railHeader?: React.ReactNode;
  /** Collapse the rail zone down to a slim expand affordance. */
  railCollapsed?: boolean;
  /** Toggle the rail collapse state. */
  onToggleRail?: () => void;
  className?: string;
}

export function CustomizableWorkspace({
  storageKey,
  defaultLayout,
  widgets,
  widgetIcon,
  renderWidget,
  editBarExtra,
  statusBar,
  toolbar = 'default',
  hideFloatingAdd = false,
  railClassName,
  railHeader,
  railCollapsed = false,
  onToggleRail,
  className,
}: CustomizableWorkspaceProps) {
  const widgetIds = useMemo(() => widgets.map(w => w.id), [widgets]);
  const workspace = useWorkspace({ storageKey, defaultLayout, knownWidgetIds: widgetIds });
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [configPlacement, setConfigPlacement] = useState<WidgetPlacement | null>(null);
  const [compact, setCompact] = useState(false);
  // Widget currently being added from the library. `mode`:
  //   'hold'  — press & drag, release to place (direct drag-and-drop)
  //   'click' — click to project a ghost, then double-click to confirm
  //             (or click the ghost), right-click / Esc to cancel.
  const [addDrag, setAddDrag] = useState<{ widgetId: string; label: string; mode: 'hold' | 'click' } | null>(null);
  const refreshAll = useRefreshAll();
  const rootRef = useRef<HTMLDivElement>(null);
  const shortcutsEnabled = !configPlacement && !libraryOpen && !addDrag;

  usePageShortcuts(rootRef, [
    { id: 'workspace-customize', label: 'Customize workspace', keys: 'shift+e', run: () => workspace.setEditMode(!workspace.editMode), enabled: shortcutsEnabled },
    { id: 'workspace-library', label: 'Open widget library', keys: 'shift+w', run: () => { workspace.setEditMode(true); setLibraryOpen(true); }, enabled: shortcutsEnabled },
    { id: 'workspace-refresh', label: 'Refresh workspace widgets', keys: 'r', run: refreshAll, enabled: shortcutsEnabled },
    { id: 'workspace-compact', label: 'Toggle compact rows', keys: 'shift+c', run: () => setCompact(v => !v), enabled: shortcutsEnabled },
  ]);

  useEffect(() => {
    if (!libraryOpen && !configPlacement) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !isKeyboardEventAvailable(event)) return;
      if (useKeyboardShortcutsStore.getState().helpOpen) return;
      event.preventDefault();
      if (configPlacement) setConfigPlacement(null);
      else setLibraryOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [libraryOpen, configPlacement]);

  // Timestamp of the last add-commit. The trailing click of a double-click
  // lands on the palette backdrop (which becomes interactive the instant the
  // add ends) — ignore backdrop closes for a moment so it doesn't shut the
  // panel mid double-click.
  const lastAddEndRef = useRef(0);
  const endAddDrag = useCallback(() => {
    lastAddEndRef.current = performance.now();
    setAddDrag(null);
  }, []);
  const closeLibrary = useCallback(() => {
    if (performance.now() - lastAddEndRef.current < 450) return;
    setLibraryOpen(false);
  }, []);

  const placed = useMemo(
    () => new Set(workspace.layout.sections.flatMap(s => s.columns.flatMap(c => c.widgets.map(w => w.widgetId)))),
    [workspace.layout],
  );

  const getDefinition = (id: string) => widgets.find(w => w.id === id);
  const activeDef = configPlacement ? getDefinition(configPlacement.widgetId) : null;

  // ── Data-hub subscription: subscribe visible widgets' dataDeps, unsubscribe
  //    hidden ones so they don't burn rate limits. ───────────────────────────
  useEffect(() => {
    const unsubs: (() => void)[] = [];
    for (const s of workspace.layout.sections) {
      for (const c of s.columns) {
        for (const w of c.widgets) {
          if (w.hidden) continue;
          const def = getDefinition(w.widgetId);
          for (const dep of def?.dataDeps ?? []) {
            unsubs.push(dataHub.subscribe(dep, () => {}));
          }
        }
      }
    }
    return () => unsubs.forEach(u => u());
  }, [workspace.layout, widgets]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={rootRef} data-keyboard-scope="Widget workspace" className={cn('relative', className)}>
      {/* Customize toggle + compact + refresh — always visible */}
      {toolbar === 'compact' ? (
        <div className="mb-3 flex items-center justify-end gap-1">
          <button
            onClick={() => setCompact(v => !v)}
            className={cn(
              'glass-button rounded-lg p-1.5 transition-all cursor-pointer',
              compact ? 'text-primary' : 'text-muted-foreground hover:text-primary',
            )}
            title="Toggle compact row height (Shift+C)"
          >
            <Settings2 size={12} />
          </button>
          <button
            onClick={refreshAll}
            className="glass-button rounded-lg p-1.5 text-muted-foreground hover:text-primary transition-all cursor-pointer"
            title="Force refresh all widgets (R)"
          >
            <RefreshCw size={12} />
          </button>
          <button
            title={workspace.editMode ? 'Done customizing (Shift+E)' : 'Customize layout (Shift+E)'}
            onClick={() => workspace.setEditMode(!workspace.editMode)}
            className={cn(
              'glass-button rounded-lg p-1.5 transition-all cursor-pointer',
              workspace.editMode ? 'text-primary' : 'text-muted-foreground hover:text-primary',
            )}
          >
            <Settings2 size={12} />
          </button>
        </div>
      ) : toolbar === 'default' ? (
        <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
          <button
            onClick={() => setCompact(v => !v)}
            className={cn(
              'glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
              compact ? 'text-primary' : 'text-muted-foreground hover:text-primary',
            )}
            title="Toggle compact row height (Shift+C)"
          >
            <Settings2 size={13} /> {compact ? 'Compact' : 'Compact'}
          </button>
          <button
            onClick={refreshAll}
            className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            title="Force refresh all widgets (R)"
          >
            <RefreshCw size={13} /> Refresh
          </button>
          <button
            title={workspace.editMode ? 'Done customizing (Shift+E)' : 'Customize layout (Shift+E)'}
            onClick={() => workspace.setEditMode(!workspace.editMode)}
            className={cn(
              'glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
              workspace.editMode ? 'text-primary' : 'text-muted-foreground hover:text-primary',
            )}
          >
            <Settings2 size={13} /> {workspace.editMode ? 'Done' : 'Customize'}
          </button>
        </div>
      ) : null}

      {/* Edit bar */}
      {workspace.editMode && (
        <div className="glass-card sticky top-0 z-30 mb-3 flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2 shadow-lg shadow-black/20 animate-fade-in">
          <span className="flex items-center gap-1.5 text-xs font-bold text-primary font-sans">
            <Settings2 size={14} /> Customizing
          </span>
          <span className="text-[10px] text-muted-foreground hidden md:inline">
            Drag to move · click to pick up, click a spot to place (double-click confirms) · drag a widget from the panel
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            {editBarExtra}
            <button
              title="Open widget library (Shift+W)"
              onClick={() => setLibraryOpen(v => !v)}
              className={cn(
                'glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
                libraryOpen ? 'text-primary' : 'text-muted-foreground hover:text-primary',
              )}
            >
              <Plus size={13} /> Widgets
            </button>
          </div>
        </div>
      )}

      {/* Canvas — wrapped in a widget-config channel so widgets can edit their
          OWN settings inline (e.g. pick the market a card shows). */}
      <WidgetConfigProvider
        value={{
          get: (id) => workspace.layout.sections
            .flatMap(s => s.columns.flatMap(c => c.widgets))
            .find(w => w.id === id)?.config ?? {},
          set: (id, patch) => workspace.ops.setWidgetConfig(id, patch),
        }}
      >
        <WorkspaceCanvas
          workspace={workspace}
          hideEditBar
          compact={compact}
          addingWidgetId={addDrag?.widgetId ?? null}
          addingLabel={addDrag?.label}
          addingMode={addDrag?.mode ?? 'hold'}
          onAddingEnd={endAddDrag}
          widgets={widgets.map(w => ({ widgetId: w.id, label: w.label, desc: w.desc }))}
          railClassName={railClassName}
          railHeader={railHeader}
          railCollapsed={railCollapsed}
          onToggleRail={onToggleRail}
          renderWidget={(widgetId, placement) => (
            <div className="relative h-full">
              {renderWidget(widgetId, placement)}
              {/* Configure — visible in edit mode, and on hover in normal mode
                  when the widget actually has settings. */}
              {(workspace.editMode || (getDefinition(widgetId)?.configFields?.length ?? 0) > 0) && (
                <button
                  onClick={() => setConfigPlacement(placement)}
                  className={cn(
                    'absolute right-2 bottom-2 z-30 rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground hover:text-primary cursor-pointer transition-opacity',
                    workspace.editMode ? 'opacity-100' : 'opacity-0 hover:opacity-100 group-hover/card:opacity-100',
                  )}
                  title="Configure widget"
                >
                  <Settings2 size={12} />
                </button>
              )}
            </div>
          )}
        />
      </WidgetConfigProvider>

      {/* Widget library */}
      {libraryOpen && (
        <WidgetLibrary
          widgets={widgets}
          widgetIcon={widgetIcon}
          onAdd={(id) => { workspace.ops.addWidget(id); }}
          onClose={closeLibrary}
          placed={placed}
          onStartAddDrag={(widgetId, label, mode) => setAddDrag({ widgetId, label, mode })}
          dragActive={!!addDrag}
        />
      )}

      {/* Config panel */}
      {configPlacement && activeDef && (
        <WidgetConfigPanel
          placement={configPlacement}
          getDefinition={getDefinition}
          onSave={(patch) => { workspace.ops.setWidgetConfig(configPlacement.id, patch); setConfigPlacement(null); }}
          onClose={() => setConfigPlacement(null)}
        />
      )}

      {/* Floating add-widget button in edit mode */}
      {workspace.editMode && !libraryOpen && !hideFloatingAdd && (
        <button
          onClick={() => setLibraryOpen(true)}
          className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-2xl border border-primary/40 bg-primary/15 text-primary px-4 py-2.5 text-xs font-bold shadow-lg shadow-black/30 hover:bg-primary/25 transition-all cursor-pointer"
        >
          <Plus size={14} /> Add Widget
        </button>
      )}

      {/* Bottom status bar */}
      {statusBar}
    </div>
  );
}
