'use client';

// ── Custom React Flow node ───────────────────────────────────────────────────
// A compact, icon-led node in the spirit of n8n: one identity tile, one label,
// typed ports, and hover-only actions. Appearance is driven by the registry, so
// a new node type needs no new component.

import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { cn } from '@/lib/utils';
import { AlertTriangle, Copy, MoreHorizontal, Plus, Trash2, WarningCircle } from '@/lib/icons';
import type { NodeCategory, PortDef, SideEffectClass } from '@/lib/graph-studio/types';
import type { NodeRunStatus } from '@/lib/graph-studio/execution-client';
import { portColor, sideEffectColor } from '@/lib/graph-studio/port-style';
import { nodeIcon } from './node-icons';

export interface EclipseNodeData extends Record<string, unknown> {
  label: string;
  type: string;
  version: string;
  category: NodeCategory;
  sideEffects: SideEffectClass;
  inputs: PortDef[];
  outputs: PortDef[];
  errorCount: number;
  warningCount: number;
  runStatus?: NodeRunStatus;
  onAddNext?: (nodeId: string, handle: string) => void;
  onDuplicate?: (nodeId: string) => void;
  onDelete?: (nodeId: string) => void;
  onMore?: (nodeId: string, anchor: { x: number; y: number }) => void;
}

const CATEGORY_ACCENT: Record<NodeCategory, string> = {
  trigger: '#38bdf8',
  data: '#34d399',
  transform: '#a78bfa',
  logic: '#f59e0b',
  integration: '#22d3ee',
  finance: '#2dd4bf',
  quant: '#818cf8',
  agent: '#e879f9',
  research: '#facc15',
  trading: '#fb7185',
  output: '#94a3b8',
};

const CATEGORY_LABEL: Record<NodeCategory, string> = {
  trigger: 'Trigger',
  data: 'Data',
  transform: 'Transform',
  logic: 'Logic',
  integration: 'Integration',
  finance: 'Market data',
  quant: 'Quant',
  agent: 'Agent',
  research: 'Research',
  trading: 'Trading',
  output: 'Output',
};

const RUN_TONE: Record<NodeRunStatus, { ring: string; dot: string; badge: string }> = {
  pending: { ring: 'border-white/10', dot: 'bg-slate-500', badge: 'text-slate-400' },
  ready: { ring: 'border-white/15', dot: 'bg-slate-400', badge: 'text-slate-300' },
  running: { ring: 'border-sky-400/80', dot: 'bg-sky-400 animate-pulse', badge: 'text-sky-300' },
  succeeded: { ring: 'border-emerald-500/70', dot: 'bg-emerald-400', badge: 'text-emerald-300' },
  failed: { ring: 'border-rose-500/80', dot: 'bg-rose-400', badge: 'text-rose-300' },
  cancelled: { ring: 'border-amber-400/70', dot: 'bg-amber-400', badge: 'text-amber-300' },
  skipped: { ring: 'border-white/5 opacity-55', dot: 'bg-slate-600', badge: 'text-slate-500' },
};

function portTop(index: number, count: number): string {
  return `${((index + 1) / (count + 1)) * 100}%`;
}

export function EclipseNode({ id, data, selected }: NodeProps<Node<EclipseNodeData>>) {
  const Icon = nodeIcon(undefined, data.category);
  const accent = CATEGORY_ACCENT[data.category] ?? sideEffectColor(data.sideEffects);
  const hasError = data.errorCount > 0;
  const hasWarning = !hasError && data.warningCount > 0;
  const run = data.runStatus;
  const tone = run ? RUN_TONE[run] : null;

  return (
    <div
      className={cn(
        'glass-card group/node relative w-[188px] rounded-[10px] border transition-[box-shadow,border-color] duration-150',
        tone?.ring ?? (hasError ? 'border-rose-500/70' : hasWarning ? 'border-amber-500/60' : 'border-black/10 dark:border-white/10'),
        selected
          ? 'shadow-[0_0_0_1.5px_rgba(56,189,248,0.9),0_12px_32px_rgba(0,0,0,0.35)]'
          : 'shadow-[0_4px_14px_rgba(0,0,0,0.18)]',
      )}
    >
      <span
        aria-hidden
        className="absolute bottom-2 left-0 top-2 w-[3px] rounded-r-full"
        style={{ background: accent }}
      />

      {data.inputs.map((port, i) => (
        <Handle
          key={`in-${port.id}`}
          id={port.id}
          type="target"
          position={Position.Left}
          style={{ top: portTop(i, data.inputs.length), background: portColor(port.type) }}
          className="!h-2.5 !w-2.5 !border-2 !border-background"
          title={`${port.name} · ${port.type}`}
        />
      ))}
      {data.outputs.map((port, i) => (
        <Handle
          key={`out-${port.id}`}
          id={port.id}
          type="source"
          position={Position.Right}
          style={{ top: portTop(i, data.outputs.length), background: portColor(port.type) }}
          className="!h-2.5 !w-2.5 !border-2 !border-background"
          title={`${port.name} · ${port.type}`}
        />
      ))}

      <div className="flex items-center gap-2.5 px-3 py-2.5 pl-4">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
          style={{ background: `${accent}1c`, color: accent }}
        >
          <Icon size={16} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[12.5px] font-semibold leading-tight text-foreground">{data.label}</span>
          <span className="block truncate text-[9px] font-medium uppercase tracking-wider text-muted-foreground/80">
            {CATEGORY_LABEL[data.category]}
          </span>
        </span>
        {(hasError || hasWarning) && (
          <span className={cn('shrink-0', hasError ? 'text-rose-400' : 'text-amber-400')}>
            {hasError ? <WarningCircle size={13} /> : <AlertTriangle size={13} />}
          </span>
        )}
      </div>

      {tone && (
        <span className={cn('absolute -bottom-2 right-2 flex items-center gap-1 rounded-full border border-black/10 bg-background/90 px-1.5 py-0.5 text-[8.5px] dark:border-white/10', tone.badge)}>
          <span className={cn('h-1.5 w-1.5 rounded-full', tone.dot)} />
          {run}
        </span>
      )}

      {/* Port labels appear on hover only — they keep the canvas readable. */}
      <div className="pointer-events-none absolute left-3 top-0 h-full w-16 opacity-0 transition-opacity group-hover/node:opacity-100">
        {data.inputs.map((port, i) => (
          <span
            key={`in-l-${port.id}`}
            className="absolute -translate-y-1/2 text-[9px] text-muted-foreground"
            style={{ top: portTop(i, data.inputs.length) }}
          >
            {port.name}
          </span>
        ))}
      </div>
      <div className="pointer-events-none absolute right-3 top-0 h-full w-16 text-right opacity-0 transition-opacity group-hover/node:opacity-100">
        {data.outputs.map((port, i) => (
          <span
            key={`out-l-${port.id}`}
            className="absolute right-0 -translate-y-1/2 text-[9px] text-muted-foreground"
            style={{ top: portTop(i, data.outputs.length) }}
          >
            {port.name}
          </span>
        ))}
      </div>

      {/* Add-next affordance on each output, like n8n's output "+" handle. */}
      {data.outputs.map((port, i) => (
        <button
          key={`add-${port.id}`}
          type="button"
          title={`Add a node after ${port.name}`}
          onClick={(event) => {
            event.stopPropagation();
            data.onAddNext?.(id, port.id);
          }}
          className="nodrag nopan absolute right-[-13px] z-10 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full border border-sky-400/50 bg-background/90 text-sky-500 opacity-0 shadow-sm transition-opacity hover:bg-sky-50 group-hover/node:opacity-100 dark:text-sky-300 dark:hover:bg-sky-500/20"
          style={{ top: portTop(i, data.outputs.length) }}
        >
          <Plus size={10} />
        </button>
      ))}

      {/* Hover toolbar. Kept solid: it sits inside a canvas pane, not a modal. */}
      <div className="nodrag nopan absolute -top-7 right-0 flex items-center gap-0.5 rounded-md border border-black/10 bg-background/90 p-0.5 opacity-0 shadow-md transition-opacity group-hover/node:opacity-100 dark:border-white/10">
        <button
          type="button"
          title="Duplicate node"
          onClick={(event) => {
            event.stopPropagation();
            data.onDuplicate?.(id);
          }}
          className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-white/10 hover:text-foreground"
        >
          <Copy size={10} />
        </button>
        <button
          type="button"
          title="Delete node"
          onClick={(event) => {
            event.stopPropagation();
            data.onDelete?.(id);
          }}
          className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-rose-500/15 hover:text-rose-400"
        >
          <Trash2 size={10} />
        </button>
        <button
          type="button"
          title="More actions"
          onClick={(event) => {
            event.stopPropagation();
            data.onMore?.(id, {
              x: event.clientX,
              y: event.clientY,
            });
          }}
          className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-white/10 hover:text-foreground"
        >
          <MoreHorizontal size={10} />
        </button>
      </div>
    </div>
  );
}
