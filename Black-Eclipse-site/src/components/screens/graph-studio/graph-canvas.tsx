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
import {
  Copy, HelpCircle, Layers, LayoutGrid, Maximize2, Minus, Plus, Search, Trash2,
} from '@/lib/icons';
import type { Diagnostic, PortDef, WorkflowIR } from '@/lib/graph-studio/types';
import type { GraphRunRecord, NodeRunStatus } from '@/lib/graph-studio/execution-client';
import { getNodeDefinition } from '@/lib/graph-studio/registry';
import { canConnect } from '@/lib/graph-studio/patches';
import { buildDuplicateNodes, buildClipboard } from '@/lib/graph-studio/edit-ops';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { EclipseNode, type EclipseNodeData } from './eclipse-node';
import { EclipseEdge, type EclipseEdgeData } from './eclipse-edge';
import { NodeSearchPanel, type NodeInsertTarget } from './node-search-panel';

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
}

function buildNodes(
  ir: WorkflowIR,
  diagnostics: Diagnostic[],
  run: GraphRunRecord | null,
  prev: Node<EclipseNodeData>[],
  callbacks: NodeCallbacks,
): Node<EclipseNodeData>[] {
  const counts = diagnosticCounts(diagnostics);
  const statuses = runStatuses(run);
  const prevNodes = new Map(prev.map((n) => [n.id, n]));
  // Wiring topology only. Colour comes from the live theme (`--primary`), so a
  // theme switch re-tints every node, wire and aurora together.
  const incomingCount = new Map<string, number>();
  const outgoingCount = new Map<string, number>();
  for (const edge of ir.edges) {
    incomingCount.set(edge.target, (incomingCount.get(edge.target) ?? 0) + 1);
    outgoingCount.set(edge.source, (outgoingCount.get(edge.source) ?? 0) + 1);
  }
  return ir.nodes.map((node) => {
    const def = getNodeDefinition(node.type, node.version);
    const count = counts.get(node.id) ?? { error: 0, warning: 0 };
    const previous = prevNodes.get(node.id);
    const data: EclipseNodeData = {
      label: node.label ?? def?.label ?? node.type,
      type: node.type,
      version: node.version,
      category: def?.category ?? 'transform',
      sideEffects: def?.sideEffects ?? 'none',
      inputs: (def?.inputs ?? []) as PortDef[],
      outputs: (def?.outputs ?? []) as PortDef[],
      errorCount: count.error,
      warningCount: count.warning,
      runStatus: statuses.get(node.id),
      accent: 'var(--primary)',
      hasIncoming: (incomingCount.get(node.id) ?? 0) > 0,
      hasOutgoing: (outgoingCount.get(node.id) ?? 0) > 0,
      ...callbacks,
    };
    return {
      id: node.id,
      type: 'eclipse',
      // Keep the live drag position, but otherwise trust the IR — auto-layout
      // and version restore must actually move nodes.
      position: previous?.dragging ? previous.position : node.layout,
      data,
      // Selection is owned by React Flow (applied via onNodesChange); carry it
      // across rebuilds instead of deriving it from the editor store here.
      selected: previous?.selected ?? false,
    } satisfies Node<EclipseNodeData>;
  });
}

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
        <LayoutGrid size={12} />
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
              <LayoutGrid size={12} /> Tidy up
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
  const diagnostics = useGraphEditor((s) => s.diagnostics);
  const run = useGraphEditor((s) => s.run);
  const selection = useGraphEditor((s) => s.selection);
  const pendingInsert = useGraphEditor((s) => s.pendingInsert);
  const consumeInsert = useGraphEditor((s) => s.consumeInsert);
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
  const wrapperRef = useRef<HTMLDivElement>(null);
  const pointerRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

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

  const nodeCallbacks = useMemo<NodeCallbacks>(
    () => ({ onAddNext, onDuplicate: onDuplicateNode, onDelete: onDeleteNode, onMore }),
    [onAddNext, onDuplicateNode, onDeleteNode, onMore],
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
    setNodes((prev) => buildNodes(ir, diagnostics, run, prev, nodeCallbacks));
    setEdges((prev) => buildEdges(ir, run, edgeCallbacks, prev));
  }, [ir, diagnostics, run, nodeCallbacks, edgeCallbacks]);

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
      if (event.key === 'Tab' && !mod && !event.altKey && inCanvas) {
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
          onTidy={applyAutoLayout}
        />
      </ReactFlow>

      {helpOpen && (
        <div className="glass-tooltip absolute bottom-12 left-3 z-20 w-[292px] rounded-xl p-3">
          <p className="mb-2 text-[11px] font-semibold text-foreground">Canvas shortcuts</p>
          <dl className="space-y-1.5 text-[10.5px]">
            {[
              ['Pan', 'Drag canvas · Space+drag'],
              ['Zoom', 'Scroll · pinch'],
              ['Box select', 'Shift + drag'],
              ['Multi-select', 'Ctrl/Cmd + click'],
              ['Move node', 'Drag node'],
              ['Node details', 'Double-click node'],
              ['Add node', 'Tab · + Add node'],
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
        title="Add a node (Tab)"
        className="glass-card-subtle graph-accent absolute right-3 top-3 z-10 flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-semibold transition-colors"
      >
        <Plus size={13} /> Add node
      </button>

      {ir && ir.nodes.length === 0 && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <div className="pointer-events-auto flex flex-col items-center gap-3 text-center">
            <p className="text-[13px] text-muted-foreground">Start with a trigger.</p>
            <button
              type="button"
              onClick={() => openPaneSearch()}
              className="graph-accent flex items-center gap-1.5 rounded-lg border px-4 py-2 text-[12px] font-medium"
            >
              <Plus size={14} /> Add first step
            </button>
          </div>
        </div>
      )}

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
          onAutoLayout={applyAutoLayout}
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
