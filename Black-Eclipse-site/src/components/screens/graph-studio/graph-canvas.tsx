'use client';

// ── Graph canvas ─────────────────────────────────────────────────────────────
// React Flow is the RENDERER, never the source of truth. Nodes/edges are built
// FROM the canonical IR, edits are routed back through validated patches, and
// the compiler reads the IR — not this component's state.
//
// Interaction model (n8n-inspired):
//   • Tab / Ctrl+K opens a searchable "add a step" panel
//   • hovering an edge offers "+" (insert into the wire) and delete
//   • hovering a node offers add-next / duplicate / delete / more
//   • right-click the pane or a node for a context menu
//   • duplicate / copy / paste / select-all are keyboard-first

import {
  useCallback, useEffect, useMemo, useRef, useState,
  type DragEvent, type MouseEvent as ReactMouseEvent,
} from 'react';
import { createPortal } from 'react-dom';
import {
  ReactFlow, ReactFlowProvider, Background, BackgroundVariant, MiniMap,
  applyNodeChanges, applyEdgeChanges, useReactFlow,
  SelectionMode,
  type Node, type Edge, type Connection, type NodeChange, type EdgeChange,
  type OnSelectionChangeParams,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { cn } from '@/lib/utils';
import { confirmDialog } from '@/lib/ui/confirm-dialog';
import {
  Broom, Copy, HelpCircle, Layers, Maximize2, Minus, Plus, Search, Trash2,
} from '@/lib/icons';
import type { Diagnostic, PortDef, WorkflowIR } from '@/lib/graph-studio/types';
import { testNode, type GraphRunRecord, type NodeRunStatus } from '@/lib/graph-studio/execution-client';
import { getNodeDefinition } from '@/lib/graph-studio/registry';
import { fieldsFor, inlineFieldsFor } from '@/lib/graph-studio/config-fields';
import { unwiredRequiredInputs, visiblePorts } from '@/lib/graph-studio/node-ports';
import {
  canTestNode, canTestNodeWithNetwork, missingRequiredInputs, type NodeTestUiState,
} from '@/lib/graph-studio/node-test-ui';
import {
  listSchedules, SCHEDULES_CHANGED_EVENT, type WorkflowSchedule,
} from '@/lib/graph-studio/schedule-client';
import type { ScheduleNodeSummary } from '@/lib/graph-studio/schedule-summary';
import {
  listWebhooks, WEBHOOKS_CHANGED_EVENT, type WorkflowWebhook,
} from '@/lib/graph-studio/webhook-client';
import type { WebhookNodeSummary } from '@/lib/graph-studio/webhook-summary';
import { canConnect } from '@/lib/graph-studio/patches';
import { buildDuplicateNodes, buildClipboard } from '@/lib/graph-studio/edit-ops';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { EclipseNode, type EclipseNodeData } from './eclipse-node';
import { EclipseEdge, type EclipseEdgeData } from './eclipse-edge';
import { NodeSearchPanel, type NodeInsertTarget } from './node-search-panel';
import { GraphOnboarding } from './graph-onboarding';

const nodeTypes = { eclipse: EclipseNode };
const edgeTypes = { eclipse: EclipseEdge };

function diagnosticCounts(diagnostics: Diagnostic[]): Map<string, { error: number; warning: number }> {
  const map = new Map<string, { error: number; warning: number }>();
  for (const d of diagnostics) {
    if (!d.nodeId) continue;
    const entry = map.get(d.nodeId) ?? { error: 0, warning: 0 };
    if (d.severity === 'error') entry.error += 1;
    else entry.warning += 1;
    map.set(d.nodeId, entry);
  }
  return map;
}

function runStatuses(run: GraphRunRecord | null): Map<string, NodeRunStatus> {
  const map = new Map<string, NodeRunStatus>();
  if (!run) return map;
  for (const [nodeId, status] of Object.entries(run.nodeStatus ?? {})) map.set(nodeId, status);
  for (const nodeRun of run.nodeRuns ?? []) {
    if (!map.has(nodeRun.nodeId) || run.status !== 'running') map.set(nodeRun.nodeId, nodeRun.status);
  }
  return map;
}

function selectionKey(nodeIds: string[], edgeIds: string[]): string {
  return `${nodeIds.join('|')}#${edgeIds.join('|')}`;
}

interface NodeCallbacks {
  onAddNext: (nodeId: string, handle: string) => void;
  onDuplicate: (nodeId: string) => void;
  onDelete: (nodeId: string) => void;
  onMore: (nodeId: string, anchor: { x: number; y: number }) => void;
  onTest: (nodeId: string, anchor: { x: number; y: number }) => void;
  onToggleExpanded: (nodeId: string) => void;
  onConfigCommit: (nodeId: string, key: string, value: unknown) => void;
}

function sameStringArray(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

/**
 * Port arrays are sometimes rebuilt per render (a Switch's visible case outputs
 * depend on its config), so compare them by value — reference equality would
 * re-render every node on every graph change, and would also hide a genuine
 * rename when a case value changes.
 */
function samePorts(a: PortDef[], b: PortDef[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  return a.every((port, index) => {
    const other = b[index];
    return port.id === other.id
      && port.name === other.name
      && port.type === other.type
      && port.kind === other.kind
      && port.optional === other.optional
      && port.nullable === other.nullable;
  });
}

function sameNodeData(a: EclipseNodeData, b: EclipseNodeData): boolean {
  return (
    a.label === b.label
    && a.type === b.type
    && a.version === b.version
    && a.description === b.description
    && a.category === b.category
    && a.icon === b.icon
    && a.sideEffects === b.sideEffects
    && samePorts(a.inputs, b.inputs)
    && samePorts(a.outputs, b.outputs)
    && a.config === b.config
    && a.inlineFields === b.inlineFields
    && sameStringArray(a.wiredInputHandles, b.wiredInputHandles)
    && a.errorCount === b.errorCount
    && a.warningCount === b.warningCount
    && a.runStatus === b.runStatus
    && a.testState?.status === b.testState?.status
    && a.testState?.durationMs === b.testState?.durationMs
    && a.testState?.error === b.testState?.error
    && a.testState?.outputs === b.testState?.outputs
    && a.testable === b.testable
    && a.schedule?.id === b.schedule?.id
    && a.schedule?.enabled === b.schedule?.enabled
    && a.schedule?.cron === b.schedule?.cron
    && a.schedule?.timezone === b.schedule?.timezone
    && a.schedule?.nextRunAt === b.schedule?.nextRunAt
    && a.schedule?.lastStatus === b.schedule?.lastStatus
    && a.webhook?.id === b.webhook?.id
    && a.webhook?.enabled === b.webhook?.enabled
    && a.webhook?.mode === b.webhook?.mode
    && a.webhook?.version === b.webhook?.version
    && a.webhook?.endpoint === b.webhook?.endpoint
    && a.webhook?.lastStatus === b.webhook?.lastStatus
    && a.webhook?.lastReceivedAt === b.webhook?.lastReceivedAt
    && a.webhook?.lastError === b.webhook?.lastError
    && a.extraFields === b.extraFields
    && a.expanded === b.expanded
    && a.accent === b.accent
    && a.onConfigCommit === b.onConfigCommit
    && a.onAddNext === b.onAddNext
    && a.onDuplicate === b.onDuplicate
    && a.onDelete === b.onDelete
    && a.onMore === b.onMore
    && a.onTest === b.onTest
    && a.onToggleExpanded === b.onToggleExpanded
  );
}

function buildNodes(
  ir: WorkflowIR,
  diagnostics: Diagnostic[],
  run: GraphRunRecord | null,
  testStates: Record<string, NodeTestUiState>,
  expandedNodes: Record<string, boolean>,
  schedules: WorkflowSchedule[],
  webhooks: WorkflowWebhook[],
  prev: Node<EclipseNodeData>[],
  callbacks: NodeCallbacks,
): Node<EclipseNodeData>[] {
  const counts = diagnosticCounts(diagnostics);
  const statuses = runStatuses(run);
  const prevNodes = new Map(prev.map((n) => [n.id, n]));
  const wiredInputs = new Map<string, string[]>();
  const wiredOutputs = new Map<string, string[]>();
  for (const edge of ir.edges) {
    const handles = wiredInputs.get(edge.target);
    if (handles) handles.push(edge.targetHandle);
    else wiredInputs.set(edge.target, [edge.targetHandle]);
    const outHandles = wiredOutputs.get(edge.source);
    if (outHandles) outHandles.push(edge.sourceHandle);
    else wiredOutputs.set(edge.source, [edge.sourceHandle]);
  }
  const scheduleByNode = new Map(
    schedules
      .filter((schedule) => schedule.nodeId)
      .map((schedule) => [schedule.nodeId as string, schedule]),
  );
  const webhookByNode = new Map<string, WorkflowWebhook>(
    webhooks
      .filter((webhook) => webhook.nodeId)
      .map((webhook) => [webhook.nodeId as string, webhook]),
  );
  return ir.nodes.map((node) => {
    const def = getNodeDefinition(node.type, node.version);
    const count = counts.get(node.id) ?? { error: 0, warning: 0 };
    const previous = prevNodes.get(node.id);
    const wiredInputHandles = wiredInputs.get(node.id) ?? NO_HANDLES;
    // Presentation only: a Switch shows the case outputs it actually has instead
    // of all eight declared ones. Handle ids are unchanged.
    const ports = def
      ? visiblePorts(def, node, wiredOutputs.get(node.id) ?? NO_HANDLES)
      : { inputs: NO_PORTS as PortDef[], outputs: NO_PORTS as PortDef[] };
    // What the card must say "connect me" about. The validator reports the same
    // thing, but a node that looks finished while it is missing an input is the
    // failure mode this fixes.
    const unmetInputs = def
      ? unwiredRequiredInputs(def, wiredInputs.get(node.id) ?? NO_HANDLES, node.inputValues ?? {})
          .map((port) => port.name)
      : [];
    const inlineFields = inlineFieldsFor(def);
    const inlineKeys = new Set(inlineFields.map((field) => field.key));
    const extraFields = def ? fieldsFor(def).filter((field) => !inlineKeys.has(field.key)) : [];
    const linkedSchedule = node.type === 'trigger.schedule' ? scheduleByNode.get(node.id) : undefined;
    const schedule: ScheduleNodeSummary | undefined = linkedSchedule
      ? {
          id: linkedSchedule.id,
          cron: linkedSchedule.cron,
          timezone: linkedSchedule.timezone,
          enabled: linkedSchedule.enabled,
          nextRunAt: linkedSchedule.nextRunAt,
          lastStatus: linkedSchedule.lastStatus,
          lastError: linkedSchedule.lastError,
          catchUp: linkedSchedule.catchUp,
        }
      : undefined;
    const linkedWebhook = node.type === 'trigger.webhook' ? webhookByNode.get(node.id) : undefined;
    const webhook: WebhookNodeSummary | undefined = linkedWebhook
      ? {
          id: linkedWebhook.id,
          enabled: linkedWebhook.enabled,
          mode: linkedWebhook.mode,
          version: linkedWebhook.version,
          endpoint: linkedWebhook.endpoint,
          lastStatus: linkedWebhook.lastStatus,
          lastReceivedAt: linkedWebhook.lastReceivedAt,
          lastError: linkedWebhook.lastError,
        }
      : undefined;
    const data: EclipseNodeData = {
      label: node.label ?? def?.label ?? node.type,
      type: node.type,
      version: node.version,
      description: def?.description ?? '',
      category: def?.category ?? 'transform',
      icon: def?.icon,
      sideEffects: def?.sideEffects ?? 'none',
      inputs: ports.inputs,
      outputs: ports.outputs,
      unmetInputs,
      config: node.config,
      inlineFields,
      extraFields,
      expanded: Boolean(expandedNodes[node.id]),
      wiredInputHandles,
      errorCount: count.error,
      warningCount: count.warning,
      runStatus: statuses.get(node.id),
      testState: testStates[node.id],
      testable: def ? canTestNode(def) || canTestNodeWithNetwork(def) : false,
      schedule,
      webhook,
      accent: 'var(--primary)',
      ...callbacks,
    };
    const position = previous?.dragging ? previous.position : node.layout;
    const selected = previous?.selected ?? false;
    // Reuse the previous node object when nothing it renders changed. Without
    // this, editing one config field re-renders every node on the canvas.
    if (
      previous
      && sameNodeData(previous.data, data)
      && previous.position.x === position.x
      && previous.position.y === position.y
      && previous.selected === selected
    ) {
      return previous;
    }
    return {
      id: node.id,
      type: 'eclipse',
      position,
      data,
      // Selection is owned by React Flow (applied via onNodesChange); carry it
      // across rebuilds instead of deriving it from the editor store here.
      selected,
    } satisfies Node<EclipseNodeData>;
  });
}

const NO_PORTS: PortDef[] = [];
const NO_HANDLES: string[] = [];

function edgeRunState(run: GraphRunRecord | null, source: string, target: string): EdgeDataState {
  const statuses = runStatuses(run);
  const s = statuses.get(source);
  const t = statuses.get(target);
  if (t === 'failed') return 'failed';
  if (t === 'running' || s === 'running') return 'running';
  if (s === 'succeeded' && t === 'succeeded') return 'succeeded';
  return undefined;
}

type EdgeDataState = 'running' | 'succeeded' | 'failed' | undefined;

interface EdgeCallbacks {
  onInsert: (edgeId: string) => void;
  onDelete: (edgeId: string) => void;
}

function buildEdges(
  ir: WorkflowIR,
  run: GraphRunRecord | null,
  callbacks: EdgeCallbacks,
  prev: Edge<EclipseEdgeData>[],
): Edge<EclipseEdgeData>[] {
  const prevEdges = new Map(prev.map((edge) => [edge.id, edge]));
  return ir.edges.map((edge) => {
    const accent = 'var(--primary)';
    return {
      id: edge.id,
      source: edge.source,
      sourceHandle: edge.sourceHandle,
      target: edge.target,
      targetHandle: edge.targetHandle,
      type: 'eclipse',
      selected: prevEdges.get(edge.id)?.selected ?? false,
      data: {
        onInsert: callbacks.onInsert,
        onDelete: callbacks.onDelete,
        runState: edgeRunState(run, edge.source, edge.target),
        accent,
      },
      style: { stroke: accent, strokeWidth: 2 },
    };
  });
}

function CanvasControls({
  minimap,
  helpOpen,
  onToggleMinimap,
  onToggleHelp,
  onTidy,
}: {
  minimap: boolean;
  helpOpen: boolean;
  onToggleMinimap: () => void;
  onToggleHelp: () => void;
  onTidy: () => void;
}) {
  const { zoomIn, zoomOut, fitView, zoomTo } = useReactFlow();
  const zoom = useGraphEditor((s) => s.canvasZoom) ?? 1;
  return (
    <div className="glass-card-subtle nodrag nopan absolute bottom-3 left-3 z-10 flex items-center gap-0.5 rounded-lg border border-black/10 p-0.5 shadow-sm dark:border-white/10">
      <button type="button" title="Zoom out" onClick={() => void zoomOut({ duration: 150 })} className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-black/5 hover:text-foreground dark:hover:bg-white/10">
        <Minus size={12} />
      </button>
      <button type="button" title="Reset zoom to 100%" onClick={() => void zoomTo(1, { duration: 200 })} className="min-w-[38px] rounded-md px-1 py-0.5 text-[10px] tabular-nums text-muted-foreground hover:text-foreground">
        {Math.round(zoom * 100)}%
      </button>
      <button type="button" title="Zoom in" onClick={() => void zoomIn({ duration: 150 })} className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-black/5 hover:text-foreground dark:hover:bg-white/10">
        <Plus size={12} />
      </button>
      <span className="mx-0.5 h-4 w-px bg-black/10 dark:bg-white/10" />
      <button type="button" title="Fit view" onClick={() => void fitView({ padding: 0.25, duration: 250 })} className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-black/5 hover:text-foreground dark:hover:bg-white/10">
        <Maximize2 size={12} />
      </button>
      <button type="button" title="Tidy up layout" onClick={onTidy} className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-black/5 hover:text-foreground dark:hover:bg-white/10">
        <Broom size={12} />
      </button>
      <button type="button" title={minimap ? 'Hide minimap' : 'Show minimap'} onClick={onToggleMinimap} className={cn('flex h-6 w-6 items-center justify-center rounded-md hover:bg-black/5 dark:hover:bg-white/10', minimap ? 'text-primary' : 'text-muted-foreground')}>
        <Layers size={12} />
      </button>
      <span className="mx-0.5 h-4 w-px bg-black/10 dark:bg-white/10" />
      <button type="button" title="Canvas shortcuts" onClick={onToggleHelp} className={cn('flex h-6 w-6 items-center justify-center rounded-md hover:bg-black/5 dark:hover:bg-white/10', helpOpen ? 'text-primary' : 'text-muted-foreground')}>
        <HelpCircle size={12} />
      </button>
    </div>
  );
}

interface ContextMenuState {
  x: number;
  y: number;
  flow: { x: number; y: number };
  nodeId?: string;
}

function ContextMenu({
  state, onClose, onAddHere, onDuplicate, onCopy, onPaste, onDelete, onSelectAll, onAutoLayout, onFit,
}: {
  state: ContextMenuState;
  onClose: () => void;
  onAddHere: () => void;
  onDuplicate: () => void;
  onCopy: () => void;
  onPaste: () => void;
  onDelete: () => void;
  onSelectAll: () => void;
  onAutoLayout: () => void;
  onFit: () => void;
}) {
  const left = Math.min(state.x, window.innerWidth - 200);
  const top = Math.min(state.y, window.innerHeight - 220);
  const item = 'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] text-foreground hover:bg-white/10';
  return createPortal(
    <div className="fixed inset-0 z-[115]" onMouseDown={onClose}>
      <div
        className="glass-tooltip absolute w-[184px] rounded-lg border border-white/10 p-1"
        style={{ left, top }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        {state.nodeId ? (
          <>
            <button type="button" className={item} onClick={() => { onDuplicate(); onClose(); }}>
              <Copy size={12} /> Duplicate <span className="ml-auto text-[9px] text-muted-foreground">⌘D</span>
            </button>
            <button type="button" className={item} onClick={() => { onCopy(); onClose(); }}>
              <Copy size={12} /> Copy <span className="ml-auto text-[9px] text-muted-foreground">⌘C</span>
            </button>
            <div className="my-1 h-px bg-white/10" />
            <button type="button" className={cn(item, 'text-rose-300 hover:bg-rose-500/10')} onClick={() => { onDelete(); onClose(); }}>
              <Trash2 size={12} /> Delete
            </button>
          </>
        ) : (
          <>
            <button type="button" className={item} onClick={() => { onAddHere(); onClose(); }}>
              <Plus size={12} /> Add node here <span className="ml-auto text-[9px] text-muted-foreground">Tab</span>
            </button>
            <button type="button" className={item} onClick={() => { onPaste(); onClose(); }}>
              <Copy size={12} /> Paste <span className="ml-auto text-[9px] text-muted-foreground">⌘V</span>
            </button>
            <div className="my-1 h-px bg-white/10" />
            <button type="button" className={item} onClick={() => { onSelectAll(); onClose(); }}>
              <Search size={12} /> Select all <span className="ml-auto text-[9px] text-muted-foreground">⌘A</span>
            </button>
            <button type="button" className={item} onClick={() => { onAutoLayout(); onClose(); }}>
              <Broom size={12} /> Tidy up
            </button>
            <button type="button" className={item} onClick={() => { onFit(); onClose(); }}>
              <Maximize2 size={12} /> Fit view
            </button>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}

export interface GraphCanvasProps {
  onSave?: () => void;
  /** Open the node inspector. `null` closes it (pane click / selection clear). */
  onInspectNode?: (nodeId: string | null) => void;
}

function CanvasInner({ onSave, onInspectNode }: GraphCanvasProps) {
  const ir = useGraphEditor((s) => s.ir);
  const workflowId = useGraphEditor((s) => s.workflowId);
  const diagnostics = useGraphEditor((s) => s.diagnostics);
  const run = useGraphEditor((s) => s.run);
  const selection = useGraphEditor((s) => s.selection);
  const pendingInsert = useGraphEditor((s) => s.pendingInsert);
  const consumeInsert = useGraphEditor((s) => s.consumeInsert);
  const focusRequest = useGraphEditor((s) => s.focusRequest);
  const consumeFocus = useGraphEditor((s) => s.consumeFocus);
  const dispatch = useGraphEditor((s) => s.dispatch);
  const dispatchMany = useGraphEditor((s) => s.dispatchMany);
  const undo = useGraphEditor((s) => s.undo);
  const redo = useGraphEditor((s) => s.redo);
  const setSelection = useGraphEditor((s) => s.setSelection);
  const selectAll = useGraphEditor((s) => s.selectAll);
  const clearSelection = useGraphEditor((s) => s.clearSelection);
  const duplicateSelection = useGraphEditor((s) => s.duplicateSelection);
  const copySelection = useGraphEditor((s) => s.copySelection);
  const pasteClipboard = useGraphEditor((s) => s.pasteClipboard);
  const applyAutoLayout = useGraphEditor((s) => s.applyAutoLayout);
  const setZoom = useGraphEditor((s) => s.setCanvasZoom);
  const { screenToFlowPosition, fitView } = useReactFlow();

  const [nodes, setNodes] = useState<Node<EclipseNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge<EclipseEdgeData>[]>([]);
  const [search, setSearch] = useState<NodeInsertTarget | null>(null);
  const [menu, setMenu] = useState<ContextMenuState | null>(null);
  const [minimap, setMinimap] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [shiftDown, setShiftDown] = useState(false);
  const [testStates, setTestStates] = useState<Record<string, NodeTestUiState>>({});
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});
  const [schedules, setSchedules] = useState<WorkflowSchedule[]>([]);
  const [webhooks, setWebhooks] = useState<WorkflowWebhook[]>([]);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const pointerRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  // Schedule nodes show their live summary on the card. Refresh on workflow
  // change, after any schedule mutation, and once a minute for the next-fire
  // clock (the tick advances `nextRunAt` server-side).
  useEffect(() => {
    if (!workflowId) {
      setSchedules([]);
      return;
    }
    let live = true;
    const load = () => {
      void listSchedules(workflowId)
        .then((items) => { if (live) setSchedules(items); })
        .catch(() => {});
    };
    load();
    window.addEventListener(SCHEDULES_CHANGED_EVENT, load);
    const timer = window.setInterval(load, 60_000);
    return () => {
      live = false;
      window.removeEventListener(SCHEDULES_CHANGED_EVENT, load);
      window.clearInterval(timer);
    };
  }, [workflowId]);

  // Webhook nodes show their endpoint/arm state on the card. Refresh on workflow
  // change and after any webhook mutation (the public route writes last status).
  useEffect(() => {
    if (!workflowId) {
      setWebhooks([]);
      return;
    }
    let live = true;
    const load = () => {
      void listWebhooks(workflowId)
        .then((items) => { if (live) setWebhooks(items); })
        .catch(() => {});
    };
    load();
    window.addEventListener(WEBHOOKS_CHANGED_EVENT, load);
    const timer = window.setInterval(load, 60_000);
    return () => {
      live = false;
      window.removeEventListener(WEBHOOKS_CHANGED_EVENT, load);
      window.clearInterval(timer);
    };
  }, [workflowId]);

  const openPaneSearch = useCallback((position?: { x: number; y: number }) => {
    const rect = wrapperRef.current?.getBoundingClientRect();
    const fallback = rect
      ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
      : { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    const screen = position ?? fallback;
    setMenu(null);
    setSearch({ kind: 'pane', position: screenToFlowPosition(screen) });
  }, [screenToFlowPosition]);

  const onInsertEdge = useCallback((edgeId: string) => {
    setSearch({ kind: 'edge', edgeId });
  }, []);

  const onDeleteEdge = useCallback((edgeId: string) => {
    dispatch({ op: 'remove_edge', edgeId });
  }, [dispatch]);

  const onAddNext = useCallback((nodeId: string, handle: string) => {
    setSearch({ kind: 'output', nodeId, handle });
  }, []);

  const onDuplicateNode = useCallback((nodeId: string) => {
    const current = useGraphEditor.getState().ir;
    if (!current) return;
    const { patches, nodeIds } = buildDuplicateNodes(current, [nodeId]);
    if (patches.length === 0) return;
    if (dispatchMany(patches)) setSelection({ nodeIds, edgeIds: [] });
  }, [dispatchMany, setSelection]);

  const onDeleteNode = useCallback((nodeId: string) => {
    dispatch({ op: 'remove_node', nodeId });
  }, [dispatch]);

  const onMore = useCallback((nodeId: string, anchor: { x: number; y: number }) => {
    setMenu({ x: anchor.x, y: anchor.y, flow: screenToFlowPosition(anchor), nodeId });
  }, [screenToFlowPosition]);

  const onToggleExpanded = useCallback((nodeId: string) => {
    setExpandedNodes((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  }, []);

  // Tidy with the nodes' real rendered heights. The store can only guess when
  // called from the top bar; here we have React Flow's measurements, so tall
  // cards never get stacked on top of the next row.
  const tidyLayout = useCallback(() => {
    const heights: Record<string, number> = {};
    for (const node of nodesRef.current) {
      const height = node.measured?.height;
      if (typeof height === 'number' && height > 0) heights[node.id] = height;
    }
    applyAutoLayout(heights);
  }, [applyAutoLayout]);

  const runNodeTest = useCallback(async (nodeId: string) => {
    const state = useGraphEditor.getState();
    const node = state.ir?.nodes.find((item) => item.id === nodeId);
    if (!node) return;
    const definition = getNodeDefinition(node.type, node.version);
    if (!definition) return;

    const networkTest = definition.sideEffects === 'network';
    if (!canTestNode(definition) && !canTestNodeWithNetwork(definition)) {
      setTestStates((prev) => ({
        ...prev,
        [nodeId]: { status: 'failed', error: 'This node has side effects; test it with an authorized run.' },
      }));
      return;
    }
    if (networkTest) {
      const target = String(node.config.url ?? '').trim() || '(the configured URL)';
      const confirmed = await confirmDialog({
        title: 'This test makes a real network request.',
        description: target,
      });
      if (!confirmed) return;
    }

    // A node test reuses the last run's inputs for this node. Ports with no
    // upstream value are reported instead of silently running with null.
    const inputs = state.run?.nodeRuns?.find((item) => item.nodeId === nodeId)?.inputs ?? {};
    const missing = missingRequiredInputs(definition, inputs);
    if (missing.length > 0) {
      const error = `Missing required input${missing.length === 1 ? '' : 's'}: ${missing.join(', ')}. Run the graph once or test it from the inspector's Test tab.`;
      setTestStates((prev) => ({ ...prev, [nodeId]: { status: 'failed', error } }));
      return;
    }

    setTestStates((prev) => ({ ...prev, [nodeId]: { status: 'running' } }));
    try {
      const result = await testNode({
        nodeType: definition.type,
        version: definition.version,
        config: node.config,
        inputs,
        mode: state.ir?.settings.executionMode ?? 'research',
        allowNetwork: networkTest,
      });
      setTestStates((prev) => ({
        ...prev,
        [nodeId]: {
          status: 'succeeded',
          durationMs: result.durationMs,
          outputs: result.outputs,
          logs: result.logs,
        },
      }));
    } catch (err) {
      setTestStates((prev) => ({
        ...prev,
        [nodeId]: { status: 'failed', error: err instanceof Error ? err.message : 'Node test failed' },
      }));
    }
  }, []);

  const onConfigCommit = useCallback((nodeId: string, key: string, value: unknown) => {
    const current = useGraphEditor.getState().ir;
    const node = current?.nodes.find((item) => item.id === nodeId);
    if (!node) return;
    dispatch(
      { op: 'update_node_config', nodeId, config: { ...node.config, [key]: value } },
      { coalesceKey: `config:${nodeId}:${key}` },
    );
  }, [dispatch]);

  const nodeCallbacks = useMemo<NodeCallbacks>(
    () => ({
      onAddNext,
      onDuplicate: onDuplicateNode,
      onDelete: onDeleteNode,
      onMore,
      onTest: (nodeId) => { void runNodeTest(nodeId); },
      onToggleExpanded,
      onConfigCommit,
    }),
    [onAddNext, onDuplicateNode, onDeleteNode, onMore, onToggleExpanded, runNodeTest, onConfigCommit],
  );
  const edgeCallbacks = useMemo<EdgeCallbacks>(
    () => ({ onInsert: onInsertEdge, onDelete: onDeleteEdge }),
    [onInsertEdge, onDeleteEdge],
  );

  useEffect(() => {
    if (!ir) {
      setNodes([]);
      setEdges([]);
      return;
    }
    setNodes((prev) => buildNodes(ir, diagnostics, run, testStates, expandedNodes, schedules, webhooks, prev, nodeCallbacks));
    setEdges((prev) => buildEdges(ir, run, edgeCallbacks, prev));
  }, [ir, diagnostics, run, testStates, expandedNodes, schedules, webhooks, nodeCallbacks, edgeCallbacks]);

  // Programmatic selection (select-all / duplicate / paste) lands in the store.
  // React Flow owns selection during pointer interaction (and reports it back
  // through onSelectionChange), so this only writes when the flags actually
  // differ — otherwise a marquee drag would ping-pong nodes <> selection.
  useEffect(() => {
    // Pointer selection already reached the nodes through `onNodesChange`.
    // Only mirror the store when the change did NOT originate from React Flow
    // (select-all / duplicate / paste), which is what avoids the update loop.
    const key = selectionKey(selection.nodeIds, selection.edgeIds);
    if (flowSelectionKeyRef.current === key) {
      flowSelectionKeyRef.current = null;
      return;
    }
    const nodeIds = new Set(selection.nodeIds);
    const edgeIds = new Set(selection.edgeIds);
    setNodes((prev) => {
      let changed = false;
      const next = prev.map((node) => {
        const selected = nodeIds.has(node.id);
        if (node.selected === selected) return node;
        changed = true;
        return { ...node, selected };
      });
      return changed ? next : prev;
    });
    setEdges((prev) => {
      let changed = false;
      const next = prev.map((edge) => {
        const selected = edgeIds.has(edge.id);
        if (edge.selected === selected) return edge;
        changed = true;
        return { ...edge, selected };
      });
      return changed ? next : prev;
    });
  }, [selection.nodeIds, selection.edgeIds]);

  // Sidebar/toolbar insertions still land here (the canvas owns the viewport).
  useEffect(() => {
    if (!pendingInsert) return;
    const def = getNodeDefinition(pendingInsert.type, pendingInsert.version);
    if (def) {
      const count = useGraphEditor.getState().ir?.nodes.length ?? 0;
      dispatch({
        op: 'add_node',
        node: {
          type: def.type,
          version: def.version,
          config: def.defaultConfig(),
          layout: { x: 120 + (count % 6) * 40, y: 120 + (count % 6) * 40 },
        },
      });
    }
    consumeInsert();
  }, [pendingInsert, dispatch, consumeInsert]);

  // After the assistant applies an edit, bring the new nodes into view. The
  // short delay lets the IR → React Flow sync land first.
  useEffect(() => {
    if (!focusRequest || focusRequest.nodeIds.length === 0) return;
    const present = focusRequest.nodeIds.filter((id) => nodesRef.current.some((node) => node.id === id));
    if (present.length === 0) {
      consumeFocus();
      return;
    }
    const timer = window.setTimeout(() => {
      void fitView({
        nodes: present.map((id) => ({ id })),
        padding: 1.4,
        duration: 350,
        maxZoom: 1.15,
      });
      consumeFocus();
    }, 80);
    return () => window.clearTimeout(timer);
  }, [focusRequest, fitView, consumeFocus]);

  const onNodesChange = useCallback(
    (changes: NodeChange<Node<EclipseNodeData>>[]) => {
      setNodes((nds) => applyNodeChanges(changes, nds));
      for (const change of changes) {
        if (change.type === 'remove') dispatch({ op: 'remove_node', nodeId: change.id });
        if (change.type === 'position' && change.dragging === false && change.position) {
          dispatch({ op: 'move_node', nodeId: change.id, position: change.position });
        }
      }
    },
    [dispatch],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange<Edge<EclipseEdgeData>>[]) => {
      setEdges((eds) => applyEdgeChanges(changes, eds));
      for (const change of changes) {
        if (change.type === 'remove') dispatch({ op: 'remove_edge', edgeId: change.id });
      }
    },
    [dispatch],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) return;
      dispatch({
        op: 'add_edge',
        edge: {
          source: connection.source,
          sourceHandle: connection.sourceHandle,
          target: connection.target,
          targetHandle: connection.targetHandle,
        },
      });
    },
    [dispatch],
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      if (!ir || !connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) return false;
      return canConnect(ir, connection.source, connection.sourceHandle, connection.target, connection.targetHandle).ok;
    },
    [ir],
  );

  // Remember the last selection React Flow itself reported. Pointer selection
  // is already applied to the nodes by `onNodesChange`; the store → nodes sync
  // below must skip those echoes or a marquee drag ping-pongs forever.
  const flowSelectionKeyRef = useRef<string | null>(null);
  const onSelectionChange = useCallback(
    (params: OnSelectionChangeParams) => {
      const nodeIds = params.nodes.map((n) => n.id);
      const edgeIds = params.edges.map((e) => e.id);
      flowSelectionKeyRef.current = selectionKey(nodeIds, edgeIds);
      setSelection({ nodeIds, edgeIds });
    },
    [setSelection],
  );

  // Industry convention (n8n/Figma): a click selects, a double-click opens the
  // node details. Dragging never opens the inspector.
  const onNodeDoubleClick = useCallback((_event: ReactMouseEvent, node: Node) => {
    onInspectNode?.(node.id);
  }, [onInspectNode]);

  const onPaneClick = useCallback(() => {
    setMenu(null);
    setSearch(null);
    setHelpOpen(false);
    clearSelection();
    onInspectNode?.(null);
  }, [clearSelection, onInspectNode]);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData('application/eclipse-node');
      if (!raw) return;
      try {
        const payload = JSON.parse(raw) as { type: string; version?: string };
        const def = getNodeDefinition(payload.type, payload.version);
        if (!def) return;
        const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
        dispatch({ op: 'add_node', node: { type: def.type, version: def.version, config: def.defaultConfig(), layout: position } });
      } catch {
        /* ignore malformed drag payload */
      }
    },
    [dispatch, screenToFlowPosition],
  );

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onPaneContextMenu = useCallback((event: MouseEvent | ReactMouseEvent) => {
    event.preventDefault();
    pointerRef.current = { x: event.clientX, y: event.clientY };
    setSearch(null);
    setMenu({
      x: event.clientX,
      y: event.clientY,
      flow: screenToFlowPosition({ x: event.clientX, y: event.clientY }),
    });
  }, [screenToFlowPosition]);

  const onNodeContextMenu = useCallback((event: ReactMouseEvent, node: Node) => {
    event.preventDefault();
    pointerRef.current = { x: event.clientX, y: event.clientY };
    setSearch(null);
    setMenu({ x: event.clientX, y: event.clientY, flow: { x: node.position.x, y: node.position.y }, nodeId: node.id });
  }, []);

  // Keyboard: undo / redo / save / duplicate / copy / paste / search.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      const mod = event.ctrlKey || event.metaKey;
      if (typing) return;
      const inCanvas = !target || target === document.body || wrapperRef.current?.contains(target);
      if (event.key === 'Tab' && (event.ctrlKey || event.metaKey) && !event.altKey && inCanvas) {
        event.preventDefault();
        openPaneSearch(pointerRef.current.x || pointerRef.current.y
          ? { x: pointerRef.current.x, y: pointerRef.current.y }
          : undefined);
      } else if (mod && event.key.toLowerCase() === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
      } else if (mod && ((event.key.toLowerCase() === 'z' && event.shiftKey) || event.key.toLowerCase() === 'y')) {
        event.preventDefault();
        redo();
      } else if (mod && event.key.toLowerCase() === 's') {
        event.preventDefault();
        onSave?.();
      } else if (mod && event.key.toLowerCase() === 'd') {
        event.preventDefault();
        duplicateSelection();
      } else if (mod && event.key.toLowerCase() === 'c') {
        copySelection();
      } else if (mod && event.key.toLowerCase() === 'v') {
        event.preventDefault();
        pasteClipboard();
      } else if (mod && event.key.toLowerCase() === 'a') {
        event.preventDefault();
        selectAll();
      } else if (event.key === 'Escape') {
        setSearch(null);
        setMenu(null);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [undo, redo, onSave, duplicateSelection, copySelection, pasteClipboard, selectAll, openPaneSearch]);

  useEffect(() => {
    const track = (event: MouseEvent) => {
      pointerRef.current = { x: event.clientX, y: event.clientY };
    };
    window.addEventListener('mousemove', track);
    return () => window.removeEventListener('mousemove', track);
  }, []);

  // Crosshair while Shift is held (box-select mode), matching n8n.
  useEffect(() => {
    const down = (event: KeyboardEvent) => { if (event.key === 'Shift') setShiftDown(true); };
    const up = (event: KeyboardEvent) => { if (event.key === 'Shift') setShiftDown(false); };
    const blur = () => setShiftDown(false);
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
    };
  }, []);

  return (
    <div
      ref={wrapperRef}
      className="relative h-full w-full"
      onContextMenu={(event) => event.preventDefault()}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onSelectionChange={onSelectionChange}
        onNodeDoubleClick={onNodeDoubleClick}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onPaneContextMenu={onPaneContextMenu}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={onPaneClick}
        onViewportChange={(viewport) => setZoom(viewport.zoom)}
        deleteKeyCode={['Backspace', 'Delete']}
        multiSelectionKeyCode={['Meta', 'Control']}
        selectionMode={SelectionMode.Partial}
        // n8n-style: drag the pane to pan; hold Shift and drag to box-select.
        selectionKeyCode="Shift"
        fitView
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        className={cn('graph-canvas bg-transparent', shiftDown && 'is-selecting')}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="rgba(148,163,184,0.20)" />
        {minimap && (
          <MiniMap
            pannable
            zoomable
            className="!bottom-3 !right-3 !rounded-lg"
            maskColor="rgba(10,10,12,0.6)"
            nodeColor="rgba(148,163,184,0.5)"
          />
        )}
        <CanvasControls
          minimap={minimap}
          helpOpen={helpOpen}
          onToggleMinimap={() => setMinimap((value) => !value)}
          onToggleHelp={() => setHelpOpen((value) => !value)}
          onTidy={tidyLayout}
        />
      </ReactFlow>

      {helpOpen && (
        <div className="glass-tooltip absolute bottom-12 left-3 z-20 w-[292px] rounded-xl p-3">
          <p className="mb-2 text-[11px] font-semibold text-foreground">Reading a node</p>
          <ul className="mb-3 space-y-1 text-[10.5px] text-muted-foreground">
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full bg-primary" />
              <span>Round = a <span className="text-foreground/90">value</span>; square = a <span className="text-foreground/90">branch</span> (run control)</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-[2px] bg-primary" />
              <span>Each connector is labelled; the subtitle says what the node does</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full ring-1 ring-amber-400/60" />
              <span>Amber ring = a required input still needs connecting</span>
            </li>
          </ul>
          <p className="mb-2 text-[11px] font-semibold text-foreground">Canvas shortcuts</p>
          <dl className="space-y-1.5 text-[10.5px]">
            {[
              ['Pan', 'Drag canvas · Space+drag'],
              ['Zoom', 'Scroll · pinch'],
              ['Box select', 'Shift + drag'],
              ['Multi-select', 'Ctrl/Cmd + click'],
              ['Move node', 'Drag node'],
              ['Node details', 'Double-click node'],
              ['Add node', 'Ctrl+Tab · + Add node'],
              ['Undo / redo', 'Ctrl+Z · Ctrl+Shift+Z'],
              ['Delete', 'Backspace · Delete'],
              ['Context menu', 'Right-click'],
            ].map(([action, keys]) => (
              <div key={action} className="flex items-start justify-between gap-3">
                <dt className="text-muted-foreground">{action}</dt>
                <dd className="text-right font-medium text-foreground/90">{keys}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Right-edge add affordance — the node library is a search panel, so a
          persistent button keeps "add a step" discoverable without the old rail. */}
      <button
        type="button"
        onClick={() => openPaneSearch()}
        title="Add a node (Ctrl+Tab)"
        className="glass-card-subtle absolute right-3 top-3 z-10 flex items-center gap-2 rounded-xl border border-black/10 py-1.5 pl-1.5 pr-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-black/20 hover:text-foreground dark:border-white/10 dark:hover:border-white/20"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-black/[0.04] text-foreground dark:bg-white/[0.06]">
          <Plus size={12} />
        </span>
        <span>Add node</span>
        <kbd className="ml-1 rounded border border-black/10 bg-black/[0.03] px-1.5 py-0.5 font-mono text-[9px] font-normal text-muted-foreground/80 dark:border-white/10 dark:bg-white/[0.04]">
          Ctrl+Tab
        </kbd>
      </button>

      {ir && ir.nodes.length === 0 && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <div className="pointer-events-auto flex flex-col items-center gap-3 text-center">
            <p className="text-[13px] text-muted-foreground">Start with a trigger.</p>
            <button
              type="button"
              onClick={() => openPaneSearch()}
              className="glass-card-subtle flex items-center gap-2 rounded-xl border border-black/10 py-2 pl-2 pr-3.5 text-[12px] font-medium text-foreground transition-colors hover:border-black/20 dark:border-white/10 dark:hover:border-white/20"
            >
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-black/[0.04] dark:bg-white/[0.06]">
                <Plus size={13} />
              </span>
              Add first step
            </button>
          </div>
        </div>
      )}

      {ir && !search && <GraphOnboarding />}

      {search && (
        <NodeSearchPanel
          target={search}
          onClose={() => setSearch(null)}
        />
      )}

      {menu && (
        <ContextMenu
          state={menu}
          onClose={() => setMenu(null)}
          onAddHere={() => openPaneSearch({ x: menu.x, y: menu.y })}
          onDuplicate={() => {
            if (menu.nodeId) onDuplicateNode(menu.nodeId);
          }}
          onCopy={() => {
            if (menu.nodeId) {
              const current = useGraphEditor.getState().ir;
              if (current) useGraphEditor.setState({ clipboard: buildClipboard(current, [menu.nodeId]) });
            } else {
              copySelection();
            }
          }}
          onPaste={() => { pasteClipboard(); }}
          onDelete={() => {
            if (menu.nodeId) onDeleteNode(menu.nodeId);
          }}
          onSelectAll={selectAll}
          onAutoLayout={tidyLayout}
          onFit={() => void fitView({ padding: 0.25, duration: 250 })}
        />
      )}
    </div>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
