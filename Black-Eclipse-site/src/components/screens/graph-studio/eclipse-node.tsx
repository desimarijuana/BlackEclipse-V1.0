'use client';

// Ã¢â€â‚¬Ã¢â€â‚¬ Custom React Flow node Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
// Compact, icon-led card: a 46px identity header (icon, title, category, run
// state) plus up to two inline config fields. Ports are handles on the card's
// edge midpoints (fanned when a side has several); their names live in the
// handle tooltip so the surface stays clean. Inline fields edit the SAME
// validated config the inspector does Ã¢â‚¬â€ one renderer, two densities.

import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { cn } from '@/lib/utils';
import {
  AlertTriangle, ChevronDown, ChevronUp, Copy, Lock, MoreHorizontal, Play, Plus, Trash2, WarningCircle,
} from '@/lib/icons';
import type { ConfigFieldDef, NodeCategory, PortDef, SideEffectClass } from '@/lib/graph-studio/types';
import type { NodeRunStatus } from '@/lib/graph-studio/execution-client';
import type { NodeTestUiState } from '@/lib/graph-studio/node-test-ui';
import {
  describeSchedule, formatNextFire, type ScheduleNodeSummary,
} from '@/lib/graph-studio/schedule-summary';
import { webhookPathLabel, type WebhookNodeSummary } from '@/lib/graph-studio/webhook-summary';
import { ConfigField } from './config-field';
import { nodeIcon } from './node-icons';

export interface EclipseNodeData extends Record<string, unknown> {
  label: string;
  type: string;
  version: string;
  /** One-line "what this node does", shown under the title on the card. */
  description: string;
  category: NodeCategory;
  icon?: string;
  sideEffects: SideEffectClass;
  inputs: PortDef[];
  outputs: PortDef[];
  /** The persisted config, rendered by the inline fields. */
  config: Record<string, unknown>;
  /** At most two scalar fields shown on the card. */
  inlineFields: ConfigFieldDef[];
  /** Every field that does not fit in the two inline slots. */
  extraFields: ConfigFieldDef[];
  /** Whether the extra fields are expanded inside the node. */
  expanded: boolean;
  /** Input handles currently supplied by an edge Ã¢â‚¬â€ those fields show "From wire". */
  wiredInputHandles: string[];
  /** Required inputs nothing satisfies yet â€” the card asks for them by name. */
  unmetInputs: string[];
  errorCount: number;
  warningCount: number;
  runStatus?: NodeRunStatus;
  /** A one-off single-node test, not the graph run. */
  testState?: NodeTestUiState;
  /** Whether the safe test envelope permits this node. */
  testable: boolean;
  /** Linked schedule for a trigger.schedule node (read-only summary). */
  schedule?: ScheduleNodeSummary;
  /** Linked endpoint for a trigger.webhook node (read-only summary). */
  webhook?: WebhookNodeSummary;
  /** Hue shared by the selected outline and every wire leaving this node. */
  accent: string;
  onConfigCommit?: (nodeId: string, key: string, value: unknown) => void;
  onAddNext?: (nodeId: string, handle: string) => void;
  onDuplicate?: (nodeId: string) => void;
  onDelete?: (nodeId: string) => void;
  onMore?: (nodeId: string, anchor: { x: number; y: number }) => void;
  onTest?: (nodeId: string, anchor: { x: number; y: number }) => void;
  onToggleExpanded?: (nodeId: string) => void;
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
  skills: 'Skill',
  research: 'Research',
  trading: 'Trading',
  learning: 'Learning',
  media: 'Media',
  output: 'Output',
};

function jsonPreview(value: unknown): string {
  try {
    const text = JSON.stringify(value, null, 2);
    return text.length > 700 ? `${text.slice(0, 700)}â€¦` : text;
  } catch {
    return String(value);
  }
}

function handleTop(index: number, count: number): string {
  if (count <= 1) return '50%';
  // A card is ~50-80px tall. Spacing compresses as ports fan out, but never below
  // the height of a port label â€” overlapping labels would be worse than none.
  const step = count > 6 ? 12 : count > 4 ? 14 : 18;
  return `calc(50% + ${(index - (count - 1) / 2) * step}px)`;
}

export function EclipseNode({ id, data, selected }: NodeProps<Node<EclipseNodeData>>) {
  const Icon = nodeIcon(data.icon, data.category);
  const accent = data.accent ?? 'var(--primary)';
  const hasError = data.errorCount > 0;
  const hasWarning = !hasError && data.warningCount > 0;
  const unmet = data.unmetInputs ?? [];
  const run = data.runStatus;
  const tone = run ? RUN_TONE[run] : null;
  const test = data.testState;
  const testTone = test?.status === 'running' ? 'bg-sky-400 animate-pulse'
    : test?.status === 'succeeded' ? 'bg-emerald-400'
      : test?.status === 'failed' ? 'bg-rose-400' : null;

  return (
    <div
      style={{ ['--node-accent' as string]: accent }}
      className={cn(
        'node-card graph-node group/node relative w-[280px] rounded-[12px] transition-[box-shadow,border-color] duration-150',
        selected && 'node-selected',
        unmet.length > 0 && !hasError && 'ring-1 ring-amber-400/45',
      )}
    >
      {/* Identity: plain outline icon, title + category, quiet run-state dot. */}
      <div className="relative z-10 flex h-[46px] items-center gap-2.5 px-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
          <Icon size={19} />
        </span>
        <span className="min-w-0 flex-1">
          <span
            className="block truncate text-[13px] font-semibold leading-tight tracking-tight text-foreground"
            title={`${data.label} Ã‚Â· ${data.type}@${data.version}`}
          >
            {data.label}
          </span>
          <span
            className="mt-0.5 block truncate text-[9.5px] leading-none text-muted-foreground"
            title={`${CATEGORY_LABEL[data.category]} Â· ${data.description}`}
          >
            {data.description}
          </span>
        </span>
        {(hasError || hasWarning || unmet.length > 0) && (
          <span
            className={cn('shrink-0', hasError ? 'text-rose-400' : 'text-amber-400')}
            title={unmet.length > 0 ? `Connect: ${unmet.join(', ')}` : undefined}
          >
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
        {testTone && (
          <span
            title={test?.status === 'failed'
              ? `Node test failed: ${test.error ?? 'unknown error'}`
              : `Node test: ${test?.status}${typeof test?.durationMs === 'number' ? ` Â· ${test.durationMs} ms` : ''}`}
            aria-label={`Node test: ${test?.status}`}
            className={cn('h-1.5 w-1.5 shrink-0 rounded-full', testTone)}
          />
        )}
      </div>

      {unmet.length > 0 && (
        <div className="relative z-10 border-t border-amber-400/20 bg-amber-400/[0.06] px-3 py-1 text-[9.5px] leading-tight text-amber-200/90">
          Connect {unmet.join(', ')}
        </div>
      )}

      {/* Inline parameters â€” the values you most often change, editable in place. */}
      {/* A schedule node carries its live schedule on the card itself. */}
      {data.type === 'trigger.schedule' && (
        <div className="relative z-10 border-t border-black/10 px-3 py-2 dark:border-white/10">
          {data.schedule ? (
            <>
              <div className="flex items-center gap-1.5 text-[10px]">
                <span
                  className={cn(
                    'h-1.5 w-1.5 rounded-full',
                    data.schedule.enabled ? 'bg-emerald-400' : 'bg-slate-500',
                  )}
                />
                <span className="text-foreground">
                  {data.schedule.enabled ? 'Active' : 'Paused'}
                </span>
                <span className="ml-auto truncate text-muted-foreground">
                  {data.schedule.enabled
                    ? formatNextFire(data.schedule.nextRunAt, data.schedule.timezone) ?? 'no next fire'
                    : 'â€”'}
                </span>
              </div>
              <div
                className="mt-0.5 truncate text-[10px] text-muted-foreground"
                title={`${data.schedule.cron} Â· ${data.schedule.timezone}`}
              >
                {describeSchedule(data.schedule.cron)} Â· {data.schedule.timezone}
              </div>
              {data.schedule.lastError && (
                <div className="mt-0.5 truncate text-[9px] text-rose-300" title={data.schedule.lastError}>
                  {data.schedule.lastError}
                </div>
              )}
            </>
          ) : (
            <div className="text-[10px] text-muted-foreground">
              No schedule yet â€” open the <span className="text-foreground">Schedule</span> tab.
            </div>
          )}
        </div>
      )}

      {/* A webhook node carries its endpoint and arm state on the card. */}
      {data.type === 'trigger.webhook' && (
        <div className="relative z-10 border-t border-black/10 px-3 py-2 dark:border-white/10">
          {data.webhook ? (
            <>
              <div className="flex items-center gap-1.5 text-[10px]">
                <span
                  className={cn(
                    'h-1.5 w-1.5 rounded-full',
                    data.webhook.enabled ? 'bg-emerald-400' : 'bg-slate-500',
                  )}
                />
                <span className="text-foreground">
                  {data.webhook.enabled ? 'Active' : 'Paused'} · {data.webhook.mode === 'armed' ? 'armed' : 'safe'}
                </span>
                <span className="ml-auto truncate text-muted-foreground">
                  {data.webhook.lastStatus ?? 'never received'}
                </span>
              </div>
              <div className="mt-0.5 truncate font-mono text-[9.5px] text-muted-foreground" title={data.webhook.endpoint}>
                {webhookPathLabel(data.webhook.endpoint)}
              </div>
              {data.webhook.lastError && (
                <div className="mt-0.5 truncate text-[9px] text-rose-300" title={data.webhook.lastError}>
                  {data.webhook.lastError}
                </div>
              )}
            </>
          ) : (
            <div className="text-[10px] text-muted-foreground">
              No webhook yet — open the <span className="text-foreground">Webhook</span> tab.
            </div>
          )}
        </div>
      )}

      {data.inlineFields.length > 0 && (
        <div
          className="nodrag nopan nowheel relative z-10 space-y-1.5 border-t border-black/10 px-3 py-2 dark:border-white/10"
          onDoubleClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {data.inlineFields.map((field) => (
            <ConfigField
              key={field.key}
              field={field}
              value={data.config[field.key]}
              variant="inline"
              wired={data.wiredInputHandles.includes(field.port ?? field.key)}
              onCommit={(value) => data.onConfigCommit?.(id, field.key, value)}
            />
          ))}
        </div>
      )}

      {/* Every remaining parameter lives inside the node, Blender/ComfyUI-style. */}
      {data.expanded && data.extraFields.length > 0 && (
        <div
          className="nodrag nopan nowheel relative z-10 space-y-1.5 border-t border-black/10 px-3 py-2 dark:border-white/10"
          onDoubleClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {data.extraFields.map((field) => (
            <ConfigField
              key={field.key}
              field={field}
              value={data.config[field.key]}
              variant="inline"
              wired={data.wiredInputHandles.includes(field.port ?? field.key)}
              onCommit={(value) => data.onConfigCommit?.(id, field.key, value)}
            />
          ))}
        </div>
      )}

      {data.extraFields.length > 0 && (
        <button
          type="button"
          title={data.expanded ? 'Hide extra parameters' : 'Show all parameters in the node'}
          onClick={(event) => {
            event.stopPropagation();
            data.onToggleExpanded?.(id);
          }}
          className="nodrag nopan relative z-10 flex w-full items-center gap-1.5 border-t border-black/10 px-3 py-1 text-left text-[9.5px] text-muted-foreground transition-colors hover:text-foreground dark:border-white/10"
        >
          {data.expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
          {data.expanded
            ? 'Show less'
            : `+${data.extraFields.length} more parameter${data.extraFields.length === 1 ? '' : 's'}`}
        </button>
      )}

      {/* Ports are labelled ONLY when a node has a real choice to make. A single
          "Start"/"Value" label is noise the user has to decode; the handle's
          tooltip still names it. Multi-port nodes keep their labels because
          "if true / if false" on the card is the difference between a guess and
          a choice. Control ports are square (they gate execution); data ports
          are round. */}
      {data.inputs.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="target"
          position={Position.Left}
          style={{
            top: handleTop(index, data.inputs.length),
            background: accent,
          }}
          className={cn(
            '!z-10 !h-2.5 !w-2.5 !border-2 !border-background !left-[-5px]',
            port.kind === 'control' ? '!rounded-[2px]' : '!rounded-full',
          )}
          title={`${port.name} Â· ${port.kind === 'control' ? 'control' : port.type}${port.optional ? ' Â· optional' : ''}`}
        />
      ))}
      {data.inputs.length > 1 && data.inputs.map((port, index) => (
        <span
          key={`in-label-${port.id}`}
          className="pointer-events-none absolute left-[-9px] z-10 -translate-x-full -translate-y-1/2 whitespace-nowrap rounded bg-background/80 px-1 text-[8.5px] font-medium leading-none text-muted-foreground backdrop-blur-sm"
          style={{ top: handleTop(index, data.inputs.length) }}
        >
          {port.name}
        </span>
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
          }}
          className={cn(
            '!z-10 !h-2.5 !w-2.5 !border-2 !border-background !right-[-5px]',
            port.kind === 'control' ? '!rounded-[2px]' : '!rounded-full',
          )}
          title={`${port.name} Â· ${port.kind === 'control' ? 'control' : port.type}${port.optional ? ' Â· optional' : ''}`}
        />
      ))}
      {data.outputs.length > 1 && data.outputs.map((port, index) => (
        <span
          key={`out-label-${port.id}`}
          className={cn(
            'pointer-events-none absolute right-[-9px] z-10 max-w-[64px] translate-x-full -translate-y-1/2 truncate whitespace-nowrap rounded px-1 text-[8.5px] font-medium leading-none backdrop-blur-sm',
            port.kind === 'control'
              ? 'bg-background/85 text-foreground/90'
              : 'bg-background/70 text-muted-foreground',
          )}
          style={{ top: handleTop(index, data.outputs.length) }}
        >
          {port.name}
        </span>
      ))}

      {/* Add-next affordance follows each output handle on hover. Hidden once the
          fan is dense: overlapping 24px buttons would stack on top of each other
          and hit-test to the wrong branch. Dragging from the handle still works. */}
      {data.outputs.length <= 4 && data.outputs.map((port, index) => (
        <button
          key={`add-${port.id}`}
          type="button"
          title={`Add a node after ${port.name}`}
          onClick={(event) => {
            event.stopPropagation();
            data.onAddNext?.(id, port.id);
          }}
          style={{ top: handleTop(index, data.outputs.length) }}
          className="nodrag nopan absolute right-[-76px] z-20 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full border border-black/10 bg-background/95 text-muted-foreground opacity-0 shadow-[0_2px_10px_rgba(0,0,0,0.35)] backdrop-blur transition-all hover:scale-105 hover:border-black/20 hover:bg-white/10 hover:text-foreground group-hover/node:opacity-100 dark:border-white/15 dark:bg-[#17171b]/95 dark:hover:border-white/25"
        >
          <Plus size={11} />
        </button>
      ))}

      {/* Test result only appears after the hover play button has run. */}
      {test && (
        <div className="nodrag nopan nowheel relative z-10 border-t border-black/10 px-2.5 py-1.5 dark:border-white/10">
          <div className="flex items-center gap-1.5 text-[9px] text-muted-foreground">
            <span
              className={cn(
                'h-1.5 w-1.5 rounded-full',
                test.status === 'running' ? 'animate-pulse bg-sky-400'
                  : test.status === 'succeeded' ? 'bg-emerald-400' : 'bg-rose-400',
              )}
            />
            <span>{test.status === 'running' ? 'Testingâ€¦' : test.status}</span>
            {typeof test.durationMs === 'number' && <span>Â· {test.durationMs} ms</span>}
          </div>
          {test.error && (
            <p className="mt-1 rounded bg-rose-500/10 px-1.5 py-1 text-[9.5px] text-rose-200">
              {test.error}
            </p>
          )}
          {test.outputs && (
            <details className="mt-1">
              <summary className="cursor-pointer text-[8.5px] uppercase tracking-wider text-muted-foreground">
                Output Â· {Object.keys(test.outputs).length}
              </summary>
              <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-black/25 p-1.5 font-mono text-[9px] leading-relaxed text-slate-300">
                {jsonPreview(test.outputs)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* Hover toolbar. Kept solid: it sits inside a canvas pane, not a modal. */}
      <div className="nodrag nopan absolute -top-7 right-0 z-20 flex items-center gap-0.5 rounded-md border border-black/10 bg-background/90 p-0.5 opacity-0 shadow-md transition-opacity group-hover/node:opacity-100 group-focus-within/node:opacity-100 dark:border-white/10">
        <button
          type="button"
          title={data.testable ? 'Test this node' : 'Side-effect nodes need an authorized run'}
          disabled={!data.testable || test?.status === 'running'}
          onClick={(event) => {
            event.stopPropagation();
            data.onTest?.(id, { x: event.clientX, y: event.clientY });
          }}
          className="flex h-6 w-6 items-center justify-center rounded bg-muted text-muted-foreground hover:text-foreground disabled:opacity-30"
        >
          {data.testable ? <Play size={11} weight="fill" /> : <Lock size={11} />}
        </button>
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
