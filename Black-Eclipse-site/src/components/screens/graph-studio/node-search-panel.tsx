'use client';

// ── Node search panel (the n8n-style "add a step" overlay) ────────────────────
// One searchable overlay for every insertion gesture: the empty-canvas button,
// Tab / Ctrl+K, a node's output "+", and the "+" that appears on an edge. It
// filters the SAME registry the palette used, and when the insertion point has
// typed ports it only offers nodes that can actually be wired there.

import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';
import { CornerDownLeft, Search, X } from '@/lib/icons';
import { listNodeDefinitions, getNodeDefinition } from '@/lib/graph-studio/registry';
import type { NodeCategory, NodeDefinition, NodePosition } from '@/lib/graph-studio/types';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import {
  buildAppendToPort, buildInsertOnEdge, canAppendToPort, canInsertOnEdge, newNodeId,
} from '@/lib/graph-studio/edit-ops';
import { nodeIcon } from './node-icons';

export type NodeInsertTarget =
  | { kind: 'pane'; position: NodePosition }
  | { kind: 'edge'; edgeId: string }
  | { kind: 'output'; nodeId: string; handle: string };

const CATEGORY_LABELS: Record<NodeCategory, string> = {
  trigger: 'Triggers',
  data: 'Data',
  transform: 'Transform',
  logic: 'Logic',
  integration: 'Integrations',
  finance: 'Market data',
  quant: 'Quant',
  agent: 'Agents',
  skills: 'Skills',
  research: 'Research & evidence',
  trading: 'Paper trading',
  output: 'Output',
};

export function NodeSearchPanel({
  target,
  onClose,
  onInserted,
}: {
  target: NodeInsertTarget;
  onClose: () => void;
  onInserted?: (nodeId: string) => void;
}) {
  const ir = useGraphEditor((s) => s.ir);
  const dispatch = useGraphEditor((s) => s.dispatch);
  const dispatchMany = useGraphEditor((s) => s.dispatchMany);
  const setSelection = useGraphEditor((s) => s.setSelection);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const compatible = useMemo(() => {
    if (!ir) return [];
    const edge = target.kind === 'edge' ? ir.edges.find((item) => item.id === target.edgeId) : undefined;
    return listNodeDefinitions().filter((def) => {
      if (target.kind === 'edge') {
        return edge ? canInsertOnEdge(ir, edge, def.type, def.version) : false;
      }
      if (target.kind === 'output') {
        return canAppendToPort(ir, target.nodeId, target.handle, def.type, def.version);
      }
      return true;
    });
  }, [ir, target]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return compatible;
    return compatible.filter(
      (def) =>
        def.label.toLowerCase().includes(q) ||
        def.type.toLowerCase().includes(q) ||
        def.description.toLowerCase().includes(q),
    );
  }, [compatible, query]);

  const groups = useMemo(() => {
    const map = new Map<NodeCategory, NodeDefinition[]>();
    for (const def of results) {
      (map.get(def.category) ?? map.set(def.category, []).get(def.category)!).push(def);
    }
    return [...map.entries()];
  }, [results]);

  /**
   * What this insertion point actually is. "Insert a node" is meaningless until
   * you know the port you are plugging into — the list is already filtered to
   * compatible nodes, so the hint explains WHY it is filtered.
   */
  const hint = useMemo(() => {
    if (!ir) return null;
    if (target.kind === 'edge') {
      const edge = ir.edges.find((item) => item.id === target.edgeId);
      if (!edge) return null;
      const source = ir.nodes.find((node) => node.id === edge.source);
      const targetNode = ir.nodes.find((node) => node.id === edge.target);
      const sourceDef = source ? getNodeDefinition(source.type, source.version) : undefined;
      const targetDef = targetNode ? getNodeDefinition(targetNode.type, targetNode.version) : undefined;
      const outPort = sourceDef?.outputs.find((port) => port.id === edge.sourceHandle);
      const inPort = targetDef?.inputs.find((port) => port.id === edge.targetHandle);
      return `Between ${source?.label ?? edge.source} · ${outPort?.name ?? edge.sourceHandle} and ${inPort?.name ?? edge.targetHandle} — the new node must take ${inPort?.type ?? 'any'} in and give it back out.`;
    }
    if (target.kind === 'output') {
      const node = ir.nodes.find((item) => item.id === target.nodeId);
      const def = node ? getNodeDefinition(node.type, node.version) : undefined;
      const port = def?.outputs.find((item) => item.id === target.handle);
      const name = port?.name ?? target.handle;
      if (port?.kind === 'control') {
        return `After ${node?.label ?? target.nodeId} · ${name} — a branch (run control). Only nodes with a Run control input can follow it.`;
      }
      return `After ${node?.label ?? target.nodeId} · ${name} (${port?.type ?? 'any'}). The new node must accept that type.`;
    }
    return null;
  }, [ir, target]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const choose = (def: NodeDefinition) => {
    if (!ir) return;
    setError(null);
    if (target.kind === 'pane') {
      const id = newNodeId(ir);
      const ok = dispatch({
        op: 'add_node',
        node: {
          id,
          type: def.type,
          version: def.version,
          config: def.defaultConfig(),
          layout: target.position,
        },
      });
      if (ok) {
        setSelection({ nodeIds: [id], edgeIds: [] });
        onInserted?.(id);
        onClose();
      }
      return;
    }
    if (target.kind === 'edge') {
      const result = buildInsertOnEdge(ir, target.edgeId, def.type, def.version);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      if (dispatchMany(result.patches)) {
        setSelection({ nodeIds: [result.nodeId], edgeIds: [] });
        onInserted?.(result.nodeId);
        onClose();
      }
      return;
    }
    const result = buildAppendToPort(ir, target.nodeId, target.handle, def.type, def.version);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    if (dispatchMany(result.patches)) {
      setSelection({ nodeIds: [result.nodeId], edgeIds: [] });
      onInserted?.(result.nodeId);
      onClose();
    }
  };

  const flat = results;
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((index) => Math.min(flat.length - 1, index + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((index) => Math.max(0, index - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const def = flat[active];
      if (def) choose(def);
    }
  };

  const title =
    target.kind === 'edge'
      ? 'Insert a step into this connection'
      : target.kind === 'output'
        ? 'Add a step after this node'
        : 'Add a step';

  return createPortal(
    <div className="fixed inset-0 z-[120] flex justify-end">
      <button
        type="button"
        aria-label="Close node library"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-black/35"
      />
      <aside className="glass-drawer relative flex h-full w-full max-w-[400px] flex-col overflow-hidden border-l border-white/10 shadow-[-24px_0_80px_rgba(0,0,0,0.55)] sm:rounded-l-2xl">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-white/10 px-4 py-3">
          <div className="min-w-0">
            <p className="text-[12px] font-semibold text-foreground">{title}</p>
            <p className="mt-0.5 text-[10px] text-muted-foreground/70">
              Pick a node to insert it at the selection.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            title="Close node library"
            aria-label="Close node library"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground"
          >
            <X size={14} />
          </button>
        </div>
        <div className="flex shrink-0 items-center gap-2 border-b border-white/10 px-3 py-2.5">
          <Search size={15} className="shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search nodes…"
            className="min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground/70"
          />
          <span className="shrink-0 rounded border border-white/10 px-1.5 py-0.5 text-[9.5px] text-muted-foreground">Esc</span>
        </div>
        {hint && (
          <p className="shrink-0 border-b border-white/10 bg-white/[0.02] px-3 py-1.5 text-[10px] leading-snug text-muted-foreground">
            {hint}
          </p>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto px-2.5 py-2.5">
          {results.length === 0 && (
            <p className="px-2 py-6 text-center text-[12px] text-muted-foreground">
              {compatible.length === 0
                ? 'No node can be wired at this point. A control (branch) output only accepts a node with a Run control input, and a data output only accepts a matching type.'
                : 'No matching nodes.'}
            </p>
          )}
          {groups.map(([category, defs]) => (
            <div key={category} className="mb-2">
              <div className="mb-1 px-2 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {CATEGORY_LABELS[category]}
              </div>
              <div className="space-y-0.5">
                {defs.map((def) => {
                  const index = flat.indexOf(def);
                  const Icon = nodeIcon(def.icon, def.category);
                  return (
                    <button
                      key={`${def.type}@${def.version}`}
                      type="button"
                      onMouseEnter={() => setActive(index)}
                      onClick={() => choose(def)}
                      className={cn(
                        'flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left',
                        index === active ? 'bg-white/10' : 'hover:bg-white/5',
                      )}
                    >
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-white/10 bg-white/[0.04] text-primary">
                        <Icon size={14} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] font-medium text-foreground">{def.label}</span>
                        <span className="block truncate text-[10.5px] text-muted-foreground">{def.description}</span>
                      </span>
                      <span className="shrink-0 text-right text-[9.5px] leading-tight text-muted-foreground/70">
                        <span className="block">
                          {def.inputs.length} in · {def.outputs.length} out
                        </span>
                        <span className="block">
                          {def.outputs.some((p) => p.kind === 'control') ? 'branch' : def.type.split('.')[0]}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="flex shrink-0 items-center gap-3 border-t border-white/10 px-3 py-1.5 text-[9.5px] text-muted-foreground">
          <span className="flex items-center gap-1"><CornerDownLeft size={10} /> add</span>
          <span>↑↓ navigate</span>
          <span className="ml-auto">{results.length} node{results.length === 1 ? '' : 's'}</span>
        </div>
        {error && <p className="border-t border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-[10.5px] text-rose-200">{error}</p>}
      </aside>
    </div>,
    document.body,
  );
}
