'use client';

// ── DiagramBlock — dependency-free SVG renderer for layered diagrams ──────────
// Renders the deterministic layout from `lib/response/diagram-layout`. Read-only
// (no graph editing) — editing is not declared by the contract. Large diagrams
// scroll inside a bounded viewport and expose a text alternative for a11y.

import { useMemo } from 'react';
import { layoutDiagram } from '@/lib/response/diagram-layout';
import type { DiagramBlock as DiagramBlockType, DiagramNode } from '@/lib/response/contract';
import { cn } from '@/lib/utils';

const TONE_CLASS: Record<DiagramNode['tone'], { fill: string; stroke: string; text: string }> = {
  neutral: { fill: 'rgba(148,163,184,0.10)', stroke: 'rgba(148,163,184,0.45)', text: 'currentColor' },
  info: { fill: 'rgba(96,165,250,0.12)', stroke: 'rgba(96,165,250,0.55)', text: 'currentColor' },
  success: { fill: 'rgba(34,197,94,0.12)', stroke: 'rgba(34,197,94,0.55)', text: 'currentColor' },
  warning: { fill: 'rgba(251,191,36,0.12)', stroke: 'rgba(251,191,36,0.55)', text: 'currentColor' },
  danger: { fill: 'rgba(244,63,94,0.12)', stroke: 'rgba(244,63,94,0.55)', text: 'currentColor' },
};

export interface DiagramBlockProps {
  block: DiagramBlockType;
  className?: string;
}

export function DiagramBlock({ block, className }: DiagramBlockProps) {
  const layout = useMemo(() => layoutDiagram(block), [block]);
  const describedBy = `diagram-alt-${block.id ?? 'anon'}`;

  return (
    <figure className={cn('w-full', className)}>
      {block.title && <figcaption className="mb-2 text-sm font-semibold text-foreground">{block.title}</figcaption>}
      <div className="overflow-auto rounded-xl border border-white/10 bg-accent/10 p-2">
        <svg
          role="img"
          aria-describedby={describedBy}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          width={layout.width}
          height={layout.height}
          className="max-w-none"
        >
          <defs>
            <marker id="eclipse-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(148,163,184,0.7)" />
            </marker>
          </defs>
          {layout.edges.map((edge, i) => (
            <g key={i}>
              <path
                d={edge.path}
                fill="none"
                stroke="rgba(148,163,184,0.55)"
                strokeWidth={1.5}
                strokeDasharray={edge.dashed ? '5 4' : undefined}
                markerEnd="url(#eclipse-arrow)"
              />
              {edge.label && (
                <text x={edge.labelX} y={edge.labelY} fontSize={10} fill="#94a3b8" textAnchor="middle">
                  {edge.label}
                </text>
              )}
            </g>
          ))}
          {layout.nodes.map((node) => {
            const tone = TONE_CLASS[node.tone];
            return (
              <g key={node.id}>
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={node.height}
                  rx={10}
                  fill={tone.fill}
                  stroke={tone.stroke}
                  strokeWidth={1.25}
                />
                <text x={node.x + node.width / 2} y={node.y + node.height / 2} dominantBaseline="middle" textAnchor="middle" fontSize={12} fill="#e5e7eb">
                  {node.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption id={describedBy} className="sr-only">
        {block.description ?? `Diagram with ${layout.nodes.length} nodes and ${layout.edges.length} edges.`}
      </figcaption>
      {layout.diagnostics.length > 0 && (
        <p className="mt-1 text-[11px] text-amber-400/80">{layout.diagnostics.join(' ')}</p>
      )}
    </figure>
  );
}

export default DiagramBlock;
