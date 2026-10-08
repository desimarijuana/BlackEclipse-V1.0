'use client';

// ── Research screen — a dedicated, customizable research workspace ───────────
// A first-class Research tab (not just the chat Sources panel). It reuses the
// shared CustomizableWorkspace + the research widget catalog, and the ONE
// research state hook. Start/inspect/poll/cancel runs, read evidence, claims and
// conflicts, and enable a recurring brief — all in one surface. Nothing is
// fabricated: an empty run shows an honest empty state.

import React, { useMemo } from 'react';
import { CustomizableWorkspace } from '@/components/workspace/customizable-workspace';
import { RESEARCH_WIDGETS, RESEARCH_WIDGET_IDS, researchWidgetIcon, renderResearchWidget, researchSizing } from '@/lib/research/research-widgets';
import { useResearchScreen } from '@/lib/research/use-research-screen';
import {
  newId,
  type WorkspaceColumn,
  type WorkspaceLayout,
  type WorkspaceSection,
} from '@/lib/workspace/types';
import { rebalanceColumns } from '@/lib/workspace/pack';
import { normalizeLayout } from '@/lib/workspace/ops';

const STORAGE_KEY = 'be_ws_research_v1';

/** Build a section of one or more balanced tracks from widget ids. */
function board(widgets: string[], tracks = 3): WorkspaceSection {
  const ids = widgets.filter((w) => RESEARCH_WIDGET_IDS.includes(w));
  const columnCount = Math.max(1, Math.min(4, tracks, ids.length || 1));
  const columns: WorkspaceColumn[] = Array.from({ length: columnCount }, () => ({
    id: newId('col'),
    weight: 1,
    widgets: [],
  }));
  ids.forEach((widgetId, i) => {
    columns[i % columns.length].widgets.push({
      id: newId(`wid-${widgetId}`),
      widgetId,
      height: null,
      ...researchSizing(widgetId),
    });
  });
  rebalanceColumns(columns);
  return { id: newId('sec'), zone: 'main', columns };
}

export function defaultResearchLayout(): WorkspaceLayout {
  const layout: WorkspaceLayout = {
    version: 2,
    sections: [
      board(['research-run-form', 'research-answer'], 2),
      board(['research-runs'], 1),
      board(['research-evidence'], 1),
      board(['research-claims', 'research-conflicts'], 2),
      board(['research-graph'], 1),
      board(['research-schedule'], 1),
    ],
  };
  return normalizeLayout(layout, new Set(RESEARCH_WIDGET_IDS)) ?? layout;
}

export function ResearchScreen() {
  const state = useResearchScreen();
  const defaultLayout = useMemo(() => defaultResearchLayout(), []);

  return (
    <div className="flex h-full w-full flex-col">
      <div className="glass-card mb-4 flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
        <span className="h-6 w-1 shrink-0 rounded-full bg-primary" />
        <div className="min-w-0">
          <h1 className="font-serif text-xl font-semibold tracking-tight text-foreground">Research</h1>
          <p className="font-mono text-[10px] text-muted-foreground">
            Evidence-driven runs · {state.runs.length} total
          </p>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        <CustomizableWorkspace
          storageKey={STORAGE_KEY}
          defaultLayout={defaultLayout}
          widgets={RESEARCH_WIDGETS}
          widgetIcon={researchWidgetIcon}
          renderWidget={(widgetId) => renderResearchWidget(widgetId, state)}
        />
      </div>
    </div>
  );
}
