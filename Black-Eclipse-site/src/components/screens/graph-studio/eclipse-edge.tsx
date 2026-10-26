'use client';

// ── Custom edge ──────────────────────────────────────────────────────────────
// n8n's signature connection affordance: hover a wire to get a "+" that inserts
// a step into it, and a delete control. The edge is still a pure renderer of the
// IR — the buttons only emit the edge id back to the canvas.

import { useState } from 'react';
import {
  BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps,
} from '@xyflow/react';
import { Plus, Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';

export interface EclipseEdgeData extends Record<string, unknown> {
  onInsert?: (edgeId: string) => void;
  onDelete?: (edgeId: string) => void;
  runState?: 'running' | 'succeeded' | 'failed';
}

export function EclipseEdge({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
  style, markerEnd, selected, data,
}: EdgeProps) {
  const [hovered, setHovered] = useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, curvature: 0.25,
  });
  const runState = (data as EclipseEdgeData | undefined)?.runState;
  const active = hovered || selected;

  return (
    <g
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        interactionWidth={24}
        className={cn(runState === 'running' && 'graph-edge-running')}
        style={{
          ...style,
          stroke: runState === 'failed'
            ? 'rgba(251,113,133,0.85)'
            : runState === 'succeeded'
              ? 'rgba(52,211,153,0.8)'
              : selected
                ? 'rgba(56,189,248,0.95)'
                : style?.stroke,
          strokeWidth: active ? 2 : 1.5,
        }}
      />
      {active && (
        <EdgeLabelRenderer>
          <div
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            className="nodrag nopan pointer-events-auto absolute flex items-center gap-1"
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
          >
            <button
              type="button"
              title="Insert a node on this connection"
              onClick={(event) => {
                event.stopPropagation();
                (data as EclipseEdgeData | undefined)?.onInsert?.(id);
              }}
              className="flex h-6 w-6 items-center justify-center rounded-full border border-sky-400/40 bg-background/90 text-sky-300 shadow-md transition-colors hover:bg-sky-500/20"
            >
              <Plus size={12} />
            </button>
            <button
              type="button"
              title="Delete connection"
              onClick={(event) => {
                event.stopPropagation();
                (data as EclipseEdgeData | undefined)?.onDelete?.(id);
              }}
              className="flex h-6 w-6 items-center justify-center rounded-full border border-white/15 bg-background/90 text-muted-foreground shadow-md transition-colors hover:border-rose-400/40 hover:text-rose-300"
            >
              <Trash2 size={11} />
            </button>
          </div>
        </EdgeLabelRenderer>
      )}
    </g>
  );
}
