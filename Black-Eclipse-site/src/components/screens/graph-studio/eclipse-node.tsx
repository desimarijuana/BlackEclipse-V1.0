'use client';

// ── Custom React Flow node ────────────────────────────────────────────────────
// Compact, icon-led card: a 46px identity header (icon, title, category, run
// state) plus up to two inline config fields. Ports are handles on the card's
// edge midpoints (fanned when a side has several); their names live in the
// handle tooltip so the surface stays clean. Inline fields edit the SAME
// validated config the inspector does — one renderer, two densities.

import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { cn } from '@/lib/utils';
import { AlertTriangle, Copy, MoreHorizontal, Plus, Trash2, WarningCircle } from '@/lib/icons';
import type { ConfigFieldDef, NodeCategory, PortDef, SideEffectClass } from '@/lib/graph-studio/types';
import type { NodeRunStatus } from '@/lib/graph-studio/execution-client';
import { ConfigField } from './config-field';
import { nodeIcon } from './node-icons';

export interface EclipseNodeData extends Record<string, unknown> {
  label: string;
  type: string;
  version: string;
  category: NodeCategory;
  icon?: string;
  sideEffects: SideEffectClass;
  inputs: PortDef[];
  outputs: PortDef[];
  /** The persisted config, rendered by the inline fields. */
  config: Record<string, unknown>;
  /** At most two scalar fields shown on the card. */
  inlineFields: ConfigFieldDef[];
  /** Input handles currently supplied by an edge — those fields show "From wire". */
  wiredInputHandles: string[];
  errorCount: number;
  warningCount: number;
  runStatus?: NodeRunStatus;
  /** Hue shared by the border, the aurora and every wire leaving this node. */
  accent: string;
  hasIncoming: boolean;
  hasOutgoing: boolean;
  onConfigCommit?: (nodeId: string, key: string, value: unknown) => void;
  onAddNext?: (nodeId: string, handle: string) => void;
  onDuplicate?: (nodeId: string) => void;
  onDelete?: (nodeId: string) => void;
  onMore?: (nodeId: string, anchor: { x: number; y: number }) => void;
}

const RUN_TONE: Record<NodeRunStatus, { dot: string; badge: string }> = {
  pending: { dot: 'bg-slate-500', badge: 'text-slate-400' },
  ready: { dot: 'bg-slate-400', badge: 'text-slate-300' },
  running: { dot: 'bg-sky-400 animate-pulse', badge: 'text-sky-300' },
  succeeded: { dot: 'bg-emerald-400', badge: 'text-emerald-300' },
  failed: { dot: 'bg-rose-400', badge: 'text-rose-300' },
  cancelled: { dot: 'bg-amber-400', badge: 'text-amber-300' },
  skipped: { dot: 'bg-slate-600', badge: 'text-slate-500' },
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

function handleTop(index: number, count: number): string {
  if (count <= 1) return '50%';
  return `calc(50% + ${(index - (count - 1) / 2) * 18}px)`;
}

export function EclipseNode({ id, data, selected }: NodeProps<Node<EclipseNodeData>>) {
  const Icon = nodeIcon(data.icon, data.category);
  const accent = data.accent ?? 'var(--primary)';
  const hasError = data.errorCount > 0;
  const hasWarning = !hasError && data.warningCount > 0;
  const run = data.runStatus;
  const tone = run ? RUN_TONE[run] : null;

  return (
    <div
      style={{ ['--node-accent' as string]: accent }}
      className={cn(
        'node-card graph-node group/node relative w-[244px] rounded-[12px] transition-[box-shadow,border-color] duration-150',
        selected && 'node-selected',
      )}
    >
      {/* Connection aurora: a small live glow on whichever side is wired. */}
      {data.hasIncoming && <span className="node-aurora node-aurora--left" aria-hidden />}
      {data.hasOutgoing && <span className="node-aurora node-aurora--right" aria-hidden />}

      {/* Identity: filled icon, title + category, quiet run-state dot. */}
      <div className="relative z-10 flex h-[46px] items-center gap-2.5 px-3">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset ring-white/10"
          style={{ color: accent, background: `color-mix(in srgb, ${accent} 14%, transparent)` }}
        >
          <Icon size={20} weight="fill" />
        </span>
        <span className="min-w-0 flex-1">
          <span
            className="block truncate text-[13px] font-semibold leading-tight tracking-tight text-foreground"
            title={`${data.label} · ${data.type}@${data.version}`}
          >
            {data.label}
          </span>
          <span className="mt-0.5 block truncate text-[9.5px] leading-none text-muted-foreground">
            {CATEGORY_LABEL[data.category]}
          </span>
        </span>
        {(hasError || hasWarning) && (
          <span className={cn('shrink-0', hasError ? 'text-rose-400' : 'text-amber-400')}>
            {hasError ? <WarningCircle size={12} /> : <AlertTriangle size={12} />}
          </span>
        )}
        {tone && (
          <span
            title={`Run status: ${run}`}
            aria-label={`Run status: ${run}`}
            className={cn('h-2 w-2 shrink-0 rounded-full', tone.dot)}
          />
        )}
      </div>

      {/* Inline parameters — the values you most often change, editable in place. */}
      {data.inlineFields.length > 0 && (
        <div
          className="nodrag nopan nowheel relative z-10 space-y-1 border-t border-black/10 px-2.5 py-1.5 dark:border-white/10"
          onDoubleClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {data.inlineFields.map((field) => (
            <ConfigField
              key={field.key}
              field={field}
              value={data.config[field.key]}
              variant="inline"
              wired={data.wiredInputHandles.includes(field.key)}
              onCommit={(value) => data.onConfigCommit?.(id, field.key, value)}
            />
          ))}
        </div>
      )}

      {/* Handles on the edge midpoints — left = incoming, right = outgoing —
          fanned only when a side has several ports. Names stay in the tooltip. */}
      {data.inputs.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="target"
          position={Position.Left}
          style={{
            top: handleTop(index, data.inputs.length),
            background: accent,
            boxShadow: `0 0 6px ${accent}`,
          }}
          className="!z-10 !h-2.5 !w-2.5 !border-2 !border-background !left-[-5px]"
          title={`${port.name} · ${port.type}`}
        />
      ))}
      {data.outputs.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="source"
          position={Position.Right}
          style={{
            top: handleTop(index, data.outputs.length),
            background: accent,
            boxShadow: `0 0 6px ${accent}`,
          }}
          className="!z-10 !h-2.5 !w-2.5 !border-2 !border-background !right-[-5px]"
          title={`${port.name} · ${port.type}`}
        />
      ))}

      {/* Add-next affordance follows each output handle on hover. */}
      {data.outputs.map((port, index) => (
        <button
          key={`add-${port.id}`}
          type="button"
          title={`Add a node after ${port.name}`}
          onClick={(event) => {
            event.stopPropagation();
            data.onAddNext?.(id, port.id);
          }}
          style={{
            top: handleTop(index, data.outputs.length),
            borderColor: `color-mix(in srgb, ${accent} 55%, transparent)`,
            color: accent,
          }}
          className="nodrag nopan absolute right-[-31px] z-10 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full border bg-background/90 opacity-0 shadow-sm transition-opacity hover:bg-black/5 group-hover/node:opacity-100 dark:hover:bg-white/10"
        >
          <Plus size={10} />
        </button>
      ))}

      {/* Hover toolbar. Kept solid: it sits inside a canvas pane, not a modal. */}
      <div className="nodrag nopan absolute -top-7 right-0 z-20 flex items-center gap-0.5 rounded-md border border-black/10 bg-background/90 p-0.5 opacity-0 shadow-md transition-opacity group-hover/node:opacity-100 group-focus-within/node:opacity-100 dark:border-white/10">
        <button
          type="button"
          title="Duplicate node"
          onClick={(event) => {
            event.stopPropagation();
            data.onDuplicate?.(id);
          }}
          className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-white/10 hover:text-foreground"
        >
          <Copy size={11} />
        </button>
        <button
          type="button"
          title="Delete node"
          onClick={(event) => {
            event.stopPropagation();
            data.onDelete?.(id);
          }}
          className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-rose-500/15 hover:text-rose-400"
        >
          <Trash2 size={11} />
        </button>
        <button
          type="button"
          title="More actions"
          onClick={(event) => {
            event.stopPropagation();
            data.onMore?.(id, { x: event.clientX, y: event.clientY });
          }}
          className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-white/10 hover:text-foreground"
        >
          <MoreHorizontal size={11} />
        </button>
      </div>
    </div>
  );
}
