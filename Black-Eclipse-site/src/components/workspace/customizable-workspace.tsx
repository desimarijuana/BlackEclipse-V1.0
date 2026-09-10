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

import React, { useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Settings2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWorkspace } from '@/lib/workspace/use-workspace';
import { WorkspaceCanvas } from '@/lib/workspace/workspace-canvas';
import { dataHub, useRefreshAll } from '@/lib/workspace/data-hub';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WidgetPlacement, WorkspaceLayout } from '@/lib/workspace/types';
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
  className,
}: CustomizableWorkspaceProps) {
  const widgetIds = useMemo(() => widgets.map(w => w.id), [widgets]);
  const workspace = useWorkspace({ storageKey, defaultLayout, knownWidgetIds: widgetIds });
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [configPlacement, setConfigPlacement] = useState<WidgetPlacement | null>(null);
  const [compact, setCompact] = useState(false);
  const refreshAll = useRefreshAll();

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
    <div className={cn('relative', className)}>
      {/* Customize toggle + compact + refresh — always visible */}
      <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
        <button
          onClick={() => setCompact(v => !v)}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
            compact
              ? 'border-primary/40 bg-primary/15 text-primary'
              : 'border-white/15 dark:border-white/10 bg-accent/30 text-muted-foreground hover:text-primary hover:border-primary/40',
          )}
          title="Toggle compact row height"
        >
          <Settings2 size={13} /> {compact ? 'Compact' : 'Compact'}
        </button>
        <button
          onClick={refreshAll}
          className="inline-flex items-center gap-1.5 rounded-xl border border-white/15 dark:border-white/10 bg-accent/30 text-muted-foreground hover:text-primary hover:border-primary/40 px-3 py-1.5 text-xs font-bold transition-all cursor-pointer"
          title="Force refresh all widgets (F5)"
        >
          <RefreshCw size={13} /> Refresh
        </button>
        <button
          onClick={() => workspace.setEditMode(!workspace.editMode)}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
            workspace.editMode
              ? 'border-primary/40 bg-primary/15 text-primary'
              : 'border-white/15 dark:border-white/10 bg-accent/30 text-muted-foreground hover:text-primary hover:border-primary/40',
          )}
        >
          <Settings2 size={13} /> {workspace.editMode ? 'Done' : 'Customize'}
        </button>
      </div>

      {/* Edit bar */}
      {workspace.editMode && (
        <div className="ws-glass sticky top-0 z-30 mb-3 flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2 shadow-lg shadow-black/20 animate-fade-in">
          <span className="flex items-center gap-1.5 text-xs font-bold text-primary font-sans">
            <Settings2 size={14} /> Customizing
          </span>
          <span className="text-[10px] text-muted-foreground hidden md:inline">
            Drag a card to move it · or click a card to pick it up, then click a spot to place · Esc/right-click cancels
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            {editBarExtra}
            <button
              onClick={() => setLibraryOpen(v => !v)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
                libraryOpen
                  ? 'border-primary/40 bg-primary/15 text-primary'
                  : 'border-white/15 dark:border-white/10 bg-accent/30 hover:bg-accent/60 hover:border-primary/40 hover:text-primary text-muted-foreground',
              )}
            >
              <Plus size={13} /> Widgets
            </button>
          </div>
        </div>
      )}

      {/* Canvas */}
      <WorkspaceCanvas
        workspace={workspace}
        hideEditBar
        compact={compact}
        widgets={widgets.map(w => ({ widgetId: w.id, label: w.label, desc: w.desc }))}
        renderWidget={(widgetId, placement) => (
          <div className="relative h-full">
            {renderWidget(widgetId, placement)}
            {workspace.editMode && (
              <button
                onClick={() => setConfigPlacement(placement)}
                className="absolute right-2 bottom-2 z-20 rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground hover:text-primary cursor-pointer"
                title="Configure widget"
              >
                <Settings2 size={12} />
              </button>
            )}
          </div>
        )}
      />

      {/* Widget library */}
      {libraryOpen && (
        <WidgetLibrary
          widgets={widgets}
          widgetIcon={widgetIcon}
          onAdd={(id) => { workspace.ops.addWidget(id); }}
          onClose={() => setLibraryOpen(false)}
          placed={placed}
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
      {workspace.editMode && !libraryOpen && (
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
