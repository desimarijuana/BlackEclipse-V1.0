'use client';

// ── NodeGraphBlock — selectable node/edge graph ────────────────────────────────
// A true interactive graph (unlike the static `diagram`): nodes are focusable and
// selectable, and selecting one reveals its `detail`. It reuses the same pure,
// deterministic layered layout as `diagram-block` (no new graph engine, no
// editing — the contract declares no edit operations). Pan/zoom are local view
// state only; they never mutate the declared graph.

import { useMemo, useState } from 'react';
import { Maximize2, ZoomIn, ZoomOut } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { layoutDiagram } from '@/lib/response/diagram-layout';
import type { DiagramBlock, NodeGraphBlock as NodeGraphBlockType, NodeGraphNode } from '@/lib/response/contract';

const TONE: Record<NodeGraphNode['tone'], { fill: string; stroke: string; text: string }> = {
  neutral: { fill: 'rgba(148,163,184,0.10)', stroke: 'rgba(148,163,184,0.45)', text: '#e5e7eb' },
  info: { fill: 'rgba(96,165,250,0.14)', stroke: 'rgba(96,165,250,0.6)', text: '#e5e7eb' },
  success: { fill: 'rgba(34,197,94,0.14)', stroke: 'rgba(34,197,94,0.6)', text: '#e5e7eb' },
  warning: { fill: 'rgba(251,191,36,0.14)', stroke: 'rgba(251,191,36,0.6)', text: '#e5e7eb' },
  danger: { fill: 'rgba(244,63,94,0.14)', stroke: 'rgba(244,63,94,0.6)', text: '#e5e7eb' },
};

const ZOOM_STEPS = [0.75, 1, 1.25, 1.5, 2];
const DEFAULT_HEIGHT = 340;

export function NodeGraphBlock({ block }: { block: NodeGraphBlockType }) {
  const layout = useMemo(
    () => layoutDiagram({ nodes: block.nodes, edges: block.edges, direction: block.direction } as DiagramBlock),
    [block.nodes, block.edges, block.direction],
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [zoomIndex, setZoomIndex] = useState(1);
  const zoom = ZOOM_STEPS[zoomIndex];
  const nodeById = useMemo(() => new Map(block.nodes.map((n) => [n.id, n])), [block.nodes]);
  const selectedNode = selected ? nodeById.get(selected) ?? null : null;

  const select = (id: string) => setSelected((cur) => (cur === id ? null : id));

  return (
    <figure className="w-full">
      {block.title && <figcaption className="mb-1.5 flex flex-wrap items-center justify-between gap-2 text-sm font-semibold text-foreground">
        <span>{block.title}</span>
        <span className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Zoom out"
            onClick={() => setZoomIndex((z) => Math.max(0, z - 1))}
            disabled={zoomIndex === 0}
            className="rounded-md border border-border/50 p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
          >
            <ZoomOut size={12} />
          </button>
          <span className="w-9 text-center font-mono text-[10px] text-muted-foreground/70">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            aria-label="Zoom in"
            onClick={() => setZoomIndex((z) => Math.min(ZOOM_STEPS.length - 1, z + 1))}
            disabled={zoomIndex === ZOOM_STEPS.length - 1}
            className="rounded-md border border-border/50 p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
          >
            <ZoomIn size={12} />
          </button>
          <button
            type="button"
            aria-label="Reset zoom"
            onClick={() => setZoomIndex(1)}
            className="rounded-md border border-border/50 p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Maximize2 size={12} />
          </button>
        </span>
      </figcaption>}

      <div
        className="overflow-auto rounded-xl border border-white/10 bg-accent/10 p-2"
        style={{ maxHeight: block.height ?? DEFAULT_HEIGHT }}
      >
        <svg
          role="group"
          aria-label={block.description ?? `Interactive graph with ${layout.nodes.length} nodes and ${layout.edges.length} edges`}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          width={layout.width * zoom}
          height={layout.height * zoom}
          className="max-w-none"
        >
          <defs>
            <marker id="eclipse-graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(148,163,184,0.7)" />
            </marker>
          </defs>
          {layout.edges.map((edge, i) => (
            <g key={i} className={cn(selected && (edge.from === selected || edge.to === selected) && 'opacity-100', selected ? 'opacity-40' : 'opacity-100')}>
              <path
                d={edge.path}
                fill="none"
                stroke="rgba(148,163,184,0.55)"
                strokeWidth={1.5}
                strokeDasharray={edge.dashed ? '5 4' : undefined}
                markerEnd="url(#eclipse-graph-arrow)"
              />
              {edge.label && (
                <text x={edge.labelX} y={edge.labelY} fontSize={10} fill="#94a3b8" textAnchor="middle">
                  {edge.label}
                </text>
              )}
            </g>
          ))}
          {layout.nodes.map((node) => {
            const tone = TONE[node.tone];
            const isActive = node.id === selected;
            const source = nodeById.get(node.id);
            return (
              <g
                key={node.id}
                role="button"
                tabIndex={0}
                aria-pressed={isActive}
                aria-label={node.label + (source?.detail ? ' — has details' : '')}
                style={{ cursor: 'pointer' }}
                onClick={() => select(node.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    select(node.id);
                  }
                }}
                className="outline-none focus-visible:opacity-80"
              >
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={node.height}
                  rx={10}
                  fill={tone.fill}
                  stroke={tone.stroke}
                  strokeWidth={isActive ? 2.5 : 1.25}
                  className="transition-[stroke-width]"
                />
                <text x={`${node.x + node.width / 2}`} y={`${node.y + node.height / 2}`} dominantBaseline="middle" textAnchor="middle" fontSize={12} fill={tone.text}>
                  {node.label}
                </text>
                {source?.detail && <circle cx={node.x + node.width - 8} cy={node.y + 8} r={2.5} fill="rgba(148,163,184,0.8)" />}
              </g>
            );
          })}
        </svg>
      </div>

      {selectedNode ? (
        <div className="mt-1.5 rounded-lg border border-sky-500/30 bg-sky-500/[0.06] px-3 py-2">
          <p className="text-[12.5px] font-semibold text-foreground">{selectedNode.label}</p>
          {selectedNode.group && <p className="text-[10px] uppercase tracking-wide text-muted-foreground/70">{selectedNode.group}</p>}
          {selectedNode.detail && <p className="mt-0.5 whitespace-pre-wrap text-[12px] text-muted-foreground">{selectedNode.detail}</p>}
        </div>
      ) : (
        <p className="mt-1 text-[10px] text-muted-foreground/60">Select a node to see its details.</p>
      )}
      {layout.diagnostics.length > 0 && <p className="mt-1 text-[11px] text-amber-400/80">{layout.diagnostics.join(' ')}</p>}
    </figure>
  );
}

export default NodeGraphBlock;
