'use client';

// ── Visual Strategy Builder ──────────────────────────────────────────────────
// A dependency-free SVG/HTML canvas over the runtime strategy-graph API. It is
// a *strategy* authoring surface (data → indicators → logic → entry/exit →
// sizing/stops/risk), not a general workflow editor. On "Compile" the graph is
// sent to the Python compiler (`/quant/graph/compile`) which returns the
// canonical StrategySpec IR plus diagnostics; the UI never computes signals.
// The IR — not the graph — is the source of truth.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { backtestClient, type GraphCompileResult, type GraphNodeSpec } from '@/lib/backtest/backtest-client';
import {
  addEdge,
  addNode,
  deserialize,
  DRAFT_KEY,
  edgePath,
  fromStrategyGraph,
  moveNode,
  portPosition,
  removeEdge,
  removeNode,
  serialize,
  specMap,
  toStrategyGraph,
  updateConfig,
  type EditorNode,
  type EditorState,
  type GraphIdentity,
  type SpecMap,
} from '@/lib/backtest/graph-editor';
import { Loader2, Play, Plus, Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';

const CATEGORY_ORDER = ['data', 'indicator', 'logic', 'trading', 'sizing', 'risk'];

const DEFAULT_IDENTITY: GraphIdentity = {
  id: 'my_strategy', name: 'My Strategy', version: '1.0.0', description: '', assetClass: 'crypto',
};

function initialSpecs(): EditorState {
  return { nodes: [], edges: [] };
}

export function StrategyCanvas({ onSaved }: { onSaved?: (id: string) => void }) {
  const [specs, setSpecs] = useState<GraphNodeSpec[]>([]);
  const [map, setMap] = useState<SpecMap>({});
  const [state, setState] = useState<EditorState>(initialSpecs);
  const [identity, setIdentity] = useState<GraphIdentity>(DEFAULT_IDENTITY);
  const [selected, setSelected] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<{ node: string; port: string } | null>(null);
  const [view, setView] = useState({ x: 40, y: 40, scale: 1 });
  const [compile, setCompile] = useState<GraphCompileResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const drag = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const pan = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  // Load node registry + restore the draft.
  useEffect(() => {
    let alive = true;
    backtestClient.listGraphNodes().then((nodes) => {
      if (!alive) return;
      setSpecs(nodes);
      setMap(specMap(nodes));
    }).catch(() => undefined);
    const draft = typeof window !== 'undefined' ? window.localStorage.getItem(DRAFT_KEY) : null;
    if (draft) {
      const restored = deserialize(draft);
      if (restored) {
        setState(restored.state);
        setIdentity(restored.identity);
      }
    }
    return () => { alive = false; };
  }, []);

  // Autosave the draft.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(DRAFT_KEY, serialize(state, identity));
    } catch { /* quota — ignore */ }
  }, [state, identity]);

  const nodeById = useMemo(() => new Map(state.nodes.map((n) => [n.id, n])), [state.nodes]);
  const selectedNode = selected ? nodeById.get(selected) ?? null : null;
  const selectedSpec = selectedNode ? map[selectedNode.type] : undefined;

  const onPaletteAdd = (spec: GraphNodeSpec) => {
    setState((s) => addNode(s, spec, 80 - view.x, 80 - view.y));
    setCompile(null);
  };

  // ── Pointer interaction ────────────────────────────────────────────────────
  const onNodePointerDown = (e: React.PointerEvent, node: EditorNode) => {
    e.stopPropagation();
    setSelected(node.id);
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    drag.current = { id: node.id, dx: (e.clientX - rect.left) / view.scale, dy: (e.clientY - rect.top) / view.scale };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const onCanvasPointerMove = (e: React.PointerEvent) => {
    if (drag.current) {
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const x = (e.clientX - rect.left) / view.scale - view.x / view.scale - drag.current.dx;
      const y = (e.clientY - rect.top) / view.scale - view.y / view.scale - drag.current.dy;
      setState((s) => moveNode(s, drag.current!.id, Math.round(x), Math.round(y)));
    } else if (pan.current) {
      setView((v) => ({ ...v, x: pan.current!.vx + (e.clientX - pan.current!.x), y: pan.current!.vy + (e.clientY - pan.current!.y) }));
    }
  };

  const endDrag = () => { drag.current = null; pan.current = null; };

  const onPortClick = (node: EditorNode, kind: 'in' | 'out', port: string) => {
    if (kind === 'out') {
      setConnecting({ node: node.id, port });
      return;
    }
    if (connecting) {
      const result = addEdge(state, map, connecting.node, connecting.port, node.id, port);
      if (result.ok && result.state) {
        setState(result.state);
        setCompile(null);
        setConnecting(null);
      } else {
        setErr(result.reason ?? 'cannot connect');
        setConnecting(null);
      }
    }
  };

  const onCompile = useCallback(async () => {
    setBusy(true); setErr(null); setMsg(null); setCompile(null);
    try {
      const result = await backtestClient.compileGraph(toStrategyGraph(state, identity));
      setCompile(result);
      const errs = result.diagnostics.filter((d) => d.severity === 'error');
      setMsg(errs.length ? `${errs.length} compile error(s).` : 'Compiled successfully.');
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'compile failed');
    } finally {
      setBusy(false);
    }
  }, [state, identity]);

  const onSave = useCallback(async () => {
    if (!compile?.ok || !compile.spec) return;
    setBusy(true); setErr(null);
    try {
      const { strategy } = await backtestClient.createStrategy(compile.spec, identity.description);
      setMsg(`Saved strategy ${strategy.id} v${strategy.version}.`);
      onSaved?.(strategy.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'save failed');
    } finally {
      setBusy(false);
    }
  }, [compile, identity.description, onSaved]);

  const grouped = useMemo(() => {
    const groups = new Map<string, GraphNodeSpec[]>();
    for (const s of specs) {
      if (!groups.has(s.category)) groups.set(s.category, []);
      groups.get(s.category)!.push(s);
    }
    return [...groups.entries()].sort(
      (a, b) => CATEGORY_ORDER.indexOf(a[0]) - CATEGORY_ORDER.indexOf(b[0]),
    );
  }, [specs]);

  const errorCount = compile?.diagnostics.filter((d) => d.severity === 'error').length ?? 0;

  return (
    <div className="flex min-w-0 flex-col gap-2">
      {/* Toolbar */}
      <div className="glass-card flex flex-wrap items-end gap-2 rounded-2xl p-3">
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Id
          <input value={identity.id} onChange={(e) => setIdentity({ ...identity, id: e.target.value })}
            className="glass-card-subtle w-32 rounded-md px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Name
          <input value={identity.name} onChange={(e) => setIdentity({ ...identity, name: e.target.value })}
            className="glass-card-subtle w-40 rounded-md px-2 py-1 text-[11px] text-foreground outline-none" />
        </label>
        <label className="flex flex-col gap-1 text-[10px] text-muted-foreground">
          Version
          <input value={identity.version} onChange={(e) => setIdentity({ ...identity, version: e.target.value })}
            className="glass-card-subtle w-20 rounded-md px-2 py-1 font-mono text-[11px] text-foreground outline-none" />
        </label>
        <button type="button" onClick={() => void onCompile()} disabled={busy}
          className="glass-button-add flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Compile
        </button>
        <button type="button" onClick={() => void onSave()} disabled={busy || !compile?.ok}
          className="glass-button rounded-lg px-3 py-1.5 text-xs disabled:opacity-40">
          Save strategy
        </button>
        <button type="button" onClick={() => { setState(initialSpecs()); setCompile(null); }}
          className="glass-button rounded-lg px-3 py-1.5 text-xs">Clear</button>
        {compile && (
          <span className={cn('text-[11px]', errorCount ? 'text-amber-400' : 'text-emerald-400')}>
            {compile.ok ? 'IR valid' : `${errorCount} error(s)`}
          </span>
        )}
      </div>

      {msg && <div className="glass-card-subtle rounded-lg px-3 py-1.5 text-[11px] text-emerald-400">{msg}</div>}
      {err && <div className="glass-card-subtle rounded-lg px-3 py-1.5 text-[11px] text-amber-400">{err}</div>}

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-[200px_minmax(0,1fr)_240px]">
        {/* Palette */}
        <div className="glass-card flex max-h-[560px] flex-col gap-2 overflow-y-auto rounded-2xl p-2">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Nodes</div>
          {grouped.map(([cat, items]) => (
            <div key={cat}>
              <div className="mb-1 text-[10px] font-semibold text-foreground/80">{cat}</div>
              {items.map((s) => (
                <button key={s.type} type="button" title={s.description}
                  onClick={() => onPaletteAdd(s)}
                  className="glass-button mb-1 flex w-full items-center gap-1 rounded-md px-2 py-1 text-left text-[11px]">
                  <Plus className="h-3 w-3 shrink-0" /> <span className="truncate">{s.title}</span>
                </button>
              ))}
            </div>
          ))}
        </div>

        {/* Canvas */}
        <div
          className="glass-card relative h-[560px] overflow-hidden rounded-2xl"
          onPointerDown={(e) => { setSelected(null); setConnecting(null); pan.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; }}
          onPointerMove={onCanvasPointerMove}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        >
          <div className="absolute right-2 top-2 z-10 flex gap-1">
            <button type="button" className="glass-button rounded px-2 py-0.5 text-xs"
              onClick={(e) => { e.stopPropagation(); setView((v) => ({ ...v, scale: Math.min(2, v.scale + 0.1) })); }}>+</button>
            <button type="button" className="glass-button rounded px-2 py-0.5 text-xs"
              onClick={(e) => { e.stopPropagation(); setView((v) => ({ ...v, scale: Math.max(0.4, v.scale - 0.1) })); }}>−</button>
          </div>
          <div className="absolute left-0 top-0 origin-top-left"
            style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}>
            <svg className="pointer-events-none absolute left-0 top-0 overflow-visible" width="1" height="1">
              {state.edges.map((e, i) => {
                const fromN = nodeById.get(e.from);
                const toN = nodeById.get(e.to);
                if (!fromN || !toN) return null;
                const p0 = portPosition(fromN, map[fromN.type], 'out', e.fromPort);
                const p1 = portPosition(toN, map[toN.type], 'in', e.toPort);
                return (
                  <path key={i} d={edgePath(p0, p1)} fill="none" strokeWidth={1.5}
                    className="pointer-events-auto cursor-pointer stroke-sky-400/60 hover:stroke-rose-400"
                    onClick={(ev) => { ev.stopPropagation(); setState((s) => removeEdge(s, e.from, e.fromPort, e.to, e.toPort)); }} />
                );
              })}
            </svg>
            {state.nodes.map((node) => <CanvasNode key={node.id} node={node} spec={map[node.type]}
              selected={selected === node.id} connecting={connecting}
              onPointerDown={onNodePointerDown} onPortClick={onPortClick}
              onDelete={() => setState((s) => removeNode(s, node.id))} />)}
          </div>
        </div>

        {/* Inspector */}
        <div className="glass-card flex max-h-[560px] flex-col gap-2 overflow-y-auto rounded-2xl p-2">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Node config</div>
          {!selectedNode && <div className="text-[11px] text-muted-foreground">Select a node to edit it.</div>}
          {selectedNode && selectedSpec && (
            <>
              <div className="text-[11px] font-semibold text-foreground">{selectedSpec.title}</div>
              <div className="font-mono text-[10px] text-muted-foreground">{selectedNode.id} · {selectedNode.type}</div>
              <ConfigFields node={selectedNode} spec={selectedSpec}
                onChange={(key, value) => { setState((s) => updateConfig(s, selectedNode.id, key, value)); setCompile(null); }} />
              <button type="button" onClick={() => setState((s) => removeNode(s, selectedNode.id))}
                className="glass-button mt-1 flex items-center justify-center gap-1 rounded-md px-2 py-1 text-[11px] text-rose-300">
                <Trash2 className="h-3 w-3" /> Delete node
              </button>
            </>
          )}
          {compile && compile.diagnostics.length > 0 && (
            <div className="mt-2 border-t border-white/10 pt-2">
              <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Diagnostics</div>
              <div className="flex flex-col gap-1">
                {compile.diagnostics.slice(0, 20).map((d, i) => (
                  <div key={i} className={cn('text-[10px]', d.severity === 'error' ? 'text-amber-400' : 'text-muted-foreground')}>
                    <span className="font-mono">{d.code}</span> {d.nodeId ? `(${d.nodeId}) ` : ''}{d.message}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CanvasNode({
  node, spec, selected, connecting, onPointerDown, onPortClick, onDelete,
}: {
  node: EditorNode;
  spec: GraphNodeSpec | undefined;
  selected: boolean;
  connecting: { node: string; port: string } | null;
  onPointerDown: (e: React.PointerEvent, node: EditorNode) => void;
  onPortClick: (node: EditorNode, kind: 'in' | 'out', port: string) => void;
  onDelete: () => void;
}) {
  const width = 208;
  const rowH = 22;
  const rows = Math.max(spec?.inputs.length ?? 0, spec?.outputs.length ?? 0);
  const height = 30 + rows * rowH + 8;
  return (
    <div className="absolute select-none" style={{ left: node.x, top: node.y, width, height }}
      onPointerDown={(e) => onPointerDown(e, node)}>
      <div className={cn('h-full w-full rounded-xl border bg-[rgba(18,18,20,0.72)] px-2 py-1 backdrop-blur',
        selected ? 'border-sky-400/70' : 'border-white/12')}>
        <div className="flex items-center justify-between">
          <span className="truncate text-[11px] font-medium text-foreground">{spec?.title ?? node.type}</span>
          <button type="button" className="text-muted-foreground hover:text-rose-400"
            onPointerDown={(e) => e.stopPropagation()} onClick={onDelete}>×</button>
        </div>
        <div className="relative" style={{ height: rows * rowH }}>
          {(spec?.inputs ?? []).map((p, i) => (
            <div key={`in-${p.name}`} className="absolute left-0 flex items-center gap-1 text-[9px] text-muted-foreground"
              style={{ top: i * rowH + 3 }}>
              <span onClick={(e) => { e.stopPropagation(); onPortClick(node, 'in', p.name); }}
                className={cn('h-2.5 w-2.5 cursor-pointer rounded-full border',
                  connecting ? 'border-sky-300 bg-sky-300' : 'border-white/40 bg-black/40',
                  p.type === 'rule' ? 'border-amber-300/60' : '')}
                title={`in: ${p.name} (${p.type})`} />
              {p.name}
            </div>
          ))}
          {(spec?.outputs ?? []).map((p, i) => (
            <div key={`out-${p.name}`} className="absolute right-0 flex items-center gap-1 text-[9px] text-muted-foreground"
              style={{ top: i * rowH + 3 }}>
              <span onClick={(e) => { e.stopPropagation(); onPortClick(node, 'out', p.name); }}
                className={cn('h-2.5 w-2.5 cursor-pointer rounded-full border border-sky-300 bg-sky-500/70')}
                title={`out: ${p.name} (${p.type})`} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ConfigFields({
  node, spec, onChange,
}: {
  node: EditorNode;
  spec: GraphNodeSpec;
  onChange: (key: string, value: unknown) => void;
}) {
  const keys = Object.keys(spec.config);
  if (keys.length === 0) {
    return <div className="text-[10px] text-muted-foreground">No configuration.</div>;
  }
  return (
    <div className="flex flex-col gap-2">
      {keys.map((key) => {
        const field = (spec.config[key] ?? {}) as { type?: string; enum?: string[] };
        const value = node.config[key] ?? spec.defaults[key];
        if (field.enum) {
          return (
            <label key={key} className="flex flex-col gap-1 text-[10px] text-muted-foreground">
              {key}
              <select value={String(value ?? '')} onChange={(e) => onChange(key, e.target.value)}
                className="glass-card-subtle rounded-md px-1.5 py-1 text-[11px] text-foreground outline-none">
                {field.enum.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </label>
          );
        }
        if (field.type === 'boolean') {
          return (
            <label key={key} className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(key, e.target.checked)} />
              {key}
            </label>
          );
        }
        const numeric = field.type === 'number' || field.type === 'integer';
        return (
          <label key={key} className="flex flex-col gap-1 text-[10px] text-muted-foreground">
            {key}
            <input type={numeric ? 'number' : 'text'} value={value === undefined ? '' : String(value)}
              onChange={(e) => onChange(key, numeric ? Number(e.target.value) : e.target.value)}
              className="glass-card-subtle rounded-md px-1.5 py-1 font-mono text-[11px] text-foreground outline-none" />
          </label>
        );
      })}
    </div>
  );
}
