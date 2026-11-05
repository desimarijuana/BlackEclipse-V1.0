'use client';

// ── Custom edge ──────────────────────────────────────────────────────────────
// n8n's signature connection affordance: hover a wire to get a "+" that inserts
// a step into it, and a delete control. The edge is still a pure renderer of the
// IR — the buttons only emit the edge id back to the canvas.

import { useState } from 'react';
import {
  BaseEdge, EdgeLabelRenderer, getStraightPath, type EdgeProps,
} from '@xyflow/react';
import { Plus, Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';

export interface EclipseEdgeData extends Record<string, unknown> {
  onInsert?: (edgeId: string) => void;
  onDelete?: (edgeId: string) => void;
  runState?: 'running' | 'succeeded' | 'failed';
  /** Category accent of the source node — the wire's own hue. */
  accent?: string;
}

export function EclipseEdge({
  id, sourceX, sourceY, targetX, targetY,
  style, markerEnd, selected, data,
}: EdgeProps) {
  const [hovered, setHovered] = useState(false);
  const [edgePath, labelX, labelY] = getStraightPath({
    sourceX, sourceY, targetX, targetY,
  });
  const edgeData = data as EclipseEdgeData | undefined;
  const runState = edgeData?.runState;
  const active = hovered || selected;
  const accent = edgeData?.accent ?? 'var(--primary)';
  const stroke = runState === 'failed'
    ? 'rgba(251,113,133,0.9)'
    : runState === 'succeeded'
      ? 'rgba(52,211,153,0.85)'
      : accent;
  // Per-edge gradient so the wire fades in from the source and brightens
  // toward the target, the way the reference connections read.
  const gradientId = `eclipse-edge-grad-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`;

  return (
    <g
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <defs>
        <linearGradient
          id={gradientId}
          gradientUnits="userSpaceOnUse"
          x1={sourceX}
          y1={sourceY}
          x2={targetX}
          y2={targetY}
        >
          <stop offset="0%" style={{ stopColor: stroke, stopOpacity: 0.15 }} />
          <stop offset="45%" style={{ stopColor: stroke, stopOpacity: 0.9 }} />
          <stop offset="100%" style={{ stopColor: stroke, stopOpacity: 0.55 }} />
        </linearGradient>
      </defs>
      {/* Soft glow underlay — the wire's "aurora" bleed. */}
      <path
        d={edgePath}
        fill="none"
        strokeWidth={active ? 10 : 7}
        strokeOpacity={runState ? 0.22 : 0.14}
        strokeLinecap="round"
        style={{ stroke, filter: 'blur(3px)' }}
      />
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        interactionWidth={24}
        className={cn(runState === 'running' && 'graph-edge-running')}
        style={{
          ...style,
          stroke: `url(#${gradientId})`,
          strokeWidth: active ? 2.5 : 2,
          filter: `drop-shadow(0 0 3px ${stroke})`,
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
              className="graph-accent flex h-6 w-6 items-center justify-center rounded-full border border-white/25 bg-white/10 text-foreground shadow-lg backdrop-blur-md transition-colors hover:border-white/40 hover:bg-white/20"
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
              className="flex h-6 w-6 items-center justify-center rounded-full border border-white/20 bg-white/10 text-muted-foreground shadow-lg backdrop-blur-md transition-colors hover:border-rose-400/40 hover:bg-white/15 hover:text-rose-300"
            >
              <Trash2 size={11} />
            </button>
          </div>
        </EdgeLabelRenderer>
      )}
    </g>
  );
}
