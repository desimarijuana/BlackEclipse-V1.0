'use client';

// ── Graph canvas ─────────────────────────────────────────────────────────────
// React Flow is the RENDERER, never the source of truth. Nodes/edges are built
// FROM the canonical IR, edits are routed back through validated patches, and
// the compiler (Phase 3) reads the IR — not this component's state.

import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import {
  ReactFlow, ReactFlowProvider, Background, BackgroundVariant, Controls, MiniMap,
  applyNodeChanges, applyEdgeChanges,
  type Node, type Edge, type Connection, type NodeChange, type EdgeChange,
  type OnSelectionChangeParams, useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { Diagnostic, PortDef, WorkflowIR } from '@/lib/graph-studio/types';
import type { GraphRunRecord, NodeRunStatus } from '@/lib/graph-studio/execution-client';
import { getNodeDefinition } from '@/lib/graph-studio/registry';
import { canConnect } from '@/lib/graph-studio/patches';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { EclipseNode, type EclipseNodeData } from './eclipse-node';

const nodeTypes = { eclipse: EclipseNode };

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
  // Live progress (while running) takes precedence over the finished record.
  for (const [nodeId, status] of Object.entries(run.nodeStatus ?? {})) map.set(nodeId, status);
  for (const nodeRun of run.nodeRuns ?? []) {
    if (!map.has(nodeRun.nodeId) || run.status !== 'running') map.set(nodeRun.nodeId, nodeRun.status);
  }
  return map;
}

function buildNodes(
  ir: WorkflowIR,
  diagnostics: Diagnostic[],
  run: GraphRunRecord | null,
  prev: Node<EclipseNodeData>[],
): Node<EclipseNodeData>[] {
  const counts = diagnosticCounts(diagnostics);
  const statuses = runStatuses(run);
  const prevPos = new Map(prev.map((n) => [n.id, n.position]));
  return ir.nodes.map((node) => {
    const def = getNodeDefinition(node.type, node.version);
    const c = counts.get(node.id) ?? { error: 0, warning: 0 };
    const data: EclipseNodeData = {
      label: node.label ?? def?.label ?? node.type,
      type: node.type,
      version: node.version,
      category: def?.category ?? 'transform',
      sideEffects: def?.sideEffects ?? 'none',
      inputs: (def?.inputs ?? []) as PortDef[],
      outputs: (def?.outputs ?? []) as PortDef[],
      errorCount: c.error,
      warningCount: c.warning,
      runStatus: statuses.get(node.id),
    };
    return {
      id: node.id,
      type: 'eclipse',
      position: prevPos.get(node.id) ?? node.layout,
      data,
    } satisfies Node<EclipseNodeData>;
  });
}

function buildEdges(ir: WorkflowIR): Edge[] {
  return ir.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    sourceHandle: edge.sourceHandle,
    target: edge.target,
    targetHandle: edge.targetHandle,
    type: 'smoothstep',
    style: { stroke: 'rgba(148,163,184,0.55)', strokeWidth: 1.5 },
  }));
}

export interface GraphCanvasProps {
  onSave?: () => void;
  fitViewRef?: { current: (() => void) | null };
}

function CanvasInner({ onSave, fitViewRef }: GraphCanvasProps) {
  const ir = useGraphEditor((s) => s.ir);
  const diagnostics = useGraphEditor((s) => s.diagnostics);
  const run = useGraphEditor((s) => s.run);
  const pendingInsert = useGraphEditor((s) => s.pendingInsert);
  const consumeInsert = useGraphEditor((s) => s.consumeInsert);
  const dispatch = useGraphEditor((s) => s.dispatch);
  const undo = useGraphEditor((s) => s.undo);
  const redo = useGraphEditor((s) => s.redo);
  const setSelection = useGraphEditor((s) => s.setSelection);
  const { screenToFlowPosition } = useReactFlow();

  const [nodes, setNodes] = useState<Node<EclipseNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  useEffect(() => {
    if (!ir) {
      setNodes([]);
      setEdges([]);
      return;
    }
    setNodes((prev) => buildNodes(ir, diagnostics, run, prev));
    setEdges(buildEdges(ir));
  }, [ir, diagnostics, run]);

  // Node library insertions (from the mode panel) land here: the canvas owns the
  // viewport, so it decides where a new node appears.
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

  const { fitView } = useReactFlow();
  useEffect(() => {
    if (!fitViewRef) return;
    fitViewRef.current = () => fitView({ padding: 0.25, duration: 300 });
    return () => {
      fitViewRef.current = null;
    };
  }, [fitViewRef, fitView]);

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
    (changes: EdgeChange<Edge>[]) => {
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
      const ok = dispatch({
        op: 'add_edge',
        edge: {
          source: connection.source,
          sourceHandle: connection.sourceHandle,
          target: connection.target,
          targetHandle: connection.targetHandle,
        },
      });
      void ok;
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

  const onSelectionChange = useCallback(
    (params: OnSelectionChangeParams) => {
      setSelection({ nodeIds: params.nodes.map((n) => n.id), edgeIds: params.edges.map((e) => e.id) });
    },
    [setSelection],
  );

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

  // Keyboard: undo / redo / save (ignored while typing in a field).
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key.toLowerCase() === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
      } else if (mod && ((event.key.toLowerCase() === 'z' && event.shiftKey) || event.key.toLowerCase() === 'y')) {
        event.preventDefault();
        redo();
      } else if (mod && event.key.toLowerCase() === 's') {
        event.preventDefault();
        onSave?.();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [undo, redo, onSave]);

  const nodeTypesMemo = useMemo(() => nodeTypes, []);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypesMemo}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      isValidConnection={isValidConnection}
      onSelectionChange={onSelectionChange}
      onDrop={onDrop}
      onDragOver={onDragOver}
      fitView
      proOptions={{ hideAttribution: true }}
      className="bg-transparent"
    >
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(148,163,184,0.18)" />
      <Controls className="!bottom-4 !left-4" />
      <MiniMap
        pannable
        zoomable
        className="!bottom-4 !right-4 !rounded-lg"
        maskColor="rgba(10,10,12,0.6)"
        nodeColor="rgba(148,163,184,0.5)"
      />
    </ReactFlow>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}

