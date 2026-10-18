'use client';

// ── Graph Studio mode panel (left sidebar) ───────────────────────────────────
// Graph Studio is a DEDICATED mode: like Bots, it lists its own objects in the
// sidebar instead of a generic nav list. Two tabs — the workflow browser and
// the node library — so a graph can be opened and built entirely from here
// while the workspace shows just the canvas and its inspector.

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { WorkflowList } from './workflow-list';
import { NodePalette } from './node-palette';

type PanelTab = 'workflows' | 'nodes';

export function GraphModePanel({
  collapsed,
  onActivate,
}: {
  collapsed?: boolean;
  onActivate?: () => void;
}) {
  const [tab, setTab] = useState<PanelTab>('workflows');
  const requestInsert = useGraphEditor((s) => s.requestInsert);
  const hasWorkflow = useGraphEditor((s) => s.ir !== null);

  if (collapsed) {
    // The collapsed rail has no room for lists; the mode switcher still opens
    // the workspace tab, so nothing is unreachable.
    return null;
  }

  return (
    <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-border/10 pt-3">
      <div className="mb-2 flex shrink-0 gap-1">
        {(['workflows', 'nodes'] as PanelTab[]).map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              'flex-1 rounded-md px-2 py-1 text-[11px] capitalize',
              tab === id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {id}
          </button>
        ))}
      </div>
      {tab === 'workflows' ? (
        // Opening or creating a workflow opens the workspace too, so the panel
        // and the page never disagree about what you are editing.
        <WorkflowList onOpened={onActivate} />
      ) : (
        <div className="min-h-0 flex-1">
          {hasWorkflow ? (
            <NodePalette
              onAdd={(type, version) => {
                requestInsert(type, version);
                onActivate?.();
              }}
            />
          ) : (
            <p className="px-1 py-3 text-[11px] text-muted-foreground">
              Open or create a workflow first — the library adds nodes to the graph you are editing.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
