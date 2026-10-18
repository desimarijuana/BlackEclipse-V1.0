'use client';

// ── Custom React Flow node ───────────────────────────────────────────────────
// One renderer for every node type. Its appearance is driven entirely by the
// registry-derived data, so a new node type needs no new component. Typed ports
// render as coloured handles; the node's side-effect class tints its border.

import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { cn } from '@/lib/utils';
import { AlertTriangle, WarningCircle } from '@/lib/icons';
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
  /** Present while a run is displayed on the canvas. */
  runStatus?: NodeRunStatus;
}

const RUN_TONE: Record<NodeRunStatus, { dot: string; text: string }> = {
  pending: { dot: 'bg-slate-500', text: 'text-slate-400' },
  ready: { dot: 'bg-slate-400', text: 'text-slate-300' },
  running: { dot: 'bg-sky-400 animate-pulse', text: 'text-sky-300' },
  succeeded: { dot: 'bg-emerald-400', text: 'text-emerald-300' },
  failed: { dot: 'bg-rose-400', text: 'text-rose-300' },
  cancelled: { dot: 'bg-amber-400', text: 'text-amber-300' },
  skipped: { dot: 'bg-slate-600', text: 'text-slate-500' },
};

function portTop(index: number, count: number): string {
  return `${((index + 1) / (count + 1)) * 100}%`;
}

export function EclipseNode({ data, selected }: NodeProps<Node<EclipseNodeData>>) {
  const Icon = nodeIcon(undefined, data.category);
  const accent = sideEffectColor(data.sideEffects);
  const hasError = data.errorCount > 0;
  const hasWarning = !hasError && data.warningCount > 0;
  const run = data.runStatus;
  const runTone = run ? RUN_TONE[run] : null;
  const borderTone = runTone
    ? run === 'failed'
      ? 'border-rose-500/70'
      : run === 'running'
        ? 'border-sky-400/70'
        : run === 'succeeded'
          ? 'border-emerald-500/50'
          : 'border-white/10'
    : hasError
      ? 'border-rose-500/60'
      : hasWarning
        ? 'border-amber-500/50'
        : 'border-white/10';

  return (
    <div
      className={cn(
        'glass-card relative w-[220px] rounded-xl border px-3 py-2.5 transition-shadow',
        selected ? 'ring-2 ring-sky-400/70' : 'ring-0',
        borderTone,
      )}
      style={{ boxShadow: selected ? '0 0 0 1px rgba(56,189,248,0.35), 0 10px 30px rgba(0,0,0,0.45)' : undefined }}
    >
      {/* Inputs */}
      {data.inputs.map((port, i) => (
        <Handle
          key={`in-${port.id}`}
          id={port.id}
          type="target"
          position={Position.Left}
          style={{ top: portTop(i, data.inputs.length), background: portColor(port.type) }}
          className="!h-2.5 !w-2.5 !border-2 !border-[#0b0b0e]"
        />
      ))}
      {/* Outputs */}
      {data.outputs.map((port, i) => (
        <Handle
          key={`out-${port.id}`}
          id={port.id}
          type="source"
          position={Position.Right}
          style={{ top: portTop(i, data.outputs.length), background: portColor(port.type) }}
          className="!h-2.5 !w-2.5 !border-2 !border-[#0b0b0e]"
        />
      ))}

      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md" style={{ background: `${accent}22`, color: accent }}>
          <Icon size={13} />
        </span>
        <span className="truncate text-[12.5px] font-medium text-foreground">{data.label}</span>
        {(hasError || hasWarning) && (
          <span className={cn('ml-auto shrink-0', hasError ? 'text-rose-400' : 'text-amber-400')}>
            {hasError ? <WarningCircle size={13} /> : <AlertTriangle size={13} />}
          </span>
        )}
      </div>
      <div className="mt-1 flex items-center gap-1.5">
        <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground">{data.type} · v{data.version}</span>
        {runTone && (
          <span className={cn('flex shrink-0 items-center gap-1 text-[9.5px]', runTone.text)}>
            <span className={cn('h-1.5 w-1.5 rounded-full', runTone.dot)} />
            {run}
          </span>
        )}
      </div>

      {/* Port labels */}
      <div className="pointer-events-none absolute left-3 top-0 h-full w-16">
        {data.inputs.map((port, i) => (
          <span
            key={`in-l-${port.id}`}
            className="absolute -translate-y-1/2 text-[9.5px] text-muted-foreground"
            style={{ top: portTop(i, data.inputs.length) }}
          >
            {port.name}
          </span>
        ))}
      </div>
      <div className="pointer-events-none absolute right-3 top-0 h-full w-16 text-right">
        {data.outputs.map((port, i) => (
          <span
            key={`out-l-${port.id}`}
            className="absolute right-0 -translate-y-1/2 text-[9.5px] text-muted-foreground"
            style={{ top: portTop(i, data.outputs.length) }}
          >
            {port.name}
          </span>
        ))}
      </div>
    </div>
  );
}
