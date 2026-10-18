'use client';

// ── Node inspector ───────────────────────────────────────────────────────────
// The configuration surface for the selected node. Fields are derived from the
// definition's `defaultConfig()` shape (string / number / boolean / array /
// object); every edit is dispatched as a validated patch, so an invalid value
// is rejected and reported rather than silently stored.

import { Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { getNodeDefinition } from '@/lib/graph-studio/registry';
import { validateConfig } from '@/lib/graph-studio/validation';
import { portColor, sideEffectColor } from '@/lib/graph-studio/port-style';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import type { PortDef } from '@/lib/graph-studio/types';

function fieldType(value: unknown): 'boolean' | 'number' | 'array' | 'object' | 'string' {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (Array.isArray(value)) return 'array';
  if (value && typeof value === 'object') return 'object';
  return 'string';
}

function PortRow({ port, direction }: { port: PortDef; direction: 'in' | 'out' }) {
  return (
    <div className="flex items-center gap-2 py-0.5 text-[11px]">
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: portColor(port.type) }} />
      <span className="truncate text-foreground">{port.name}</span>
      <span className="ml-auto shrink-0 text-muted-foreground">
        {direction === 'in' ? '←' : '→'} {port.type}
        {port.optional ? ' · optional' : ''}
      </span>
    </div>
  );
}

export function NodeInspector() {
  const ir = useGraphEditor((s) => s.ir);
  const selection = useGraphEditor((s) => s.selection);
  const dispatch = useGraphEditor((s) => s.dispatch);
  const lastError = useGraphEditor((s) => s.lastError);

  const node = ir && selection.nodeIds.length === 1 ? ir.nodes.find((n) => n.id === selection.nodeIds[0]) : undefined;

  if (!node) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-[12px] text-muted-foreground">
        Select a node to configure it.
      </div>
    );
  }
  const def = getNodeDefinition(node.type, node.version);
  if (!def) {
    return <div className="px-3 py-4 text-[12px] text-rose-400">Unknown node type “{node.type}”.</div>;
  }

  const configError = validateConfig(def, node.config);
  const defaults = def.defaultConfig();

  const setConfigValue = (key: string, value: unknown) => {
    dispatch({ op: 'update_node_config', nodeId: node.id, config: { ...node.config, [key]: value } });
  };

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-white/10 px-3 py-2">
        <input
          value={node.label ?? ''}
          placeholder={def.label}
          onChange={(e) => dispatch({ op: 'update_node_label', nodeId: node.id, label: e.target.value || undefined })}
          className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1.5 text-[13px] font-medium outline-none focus:border-sky-400/50"
        />
        <div className="mt-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="truncate">{node.type} · v{node.version}</span>
          <span
            className="ml-auto shrink-0 rounded-full px-1.5 py-0.5"
            style={{ background: `${sideEffectColor(def.sideEffects)}1f`, color: sideEffectColor(def.sideEffects) }}
          >
            {def.sideEffects}
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <p className="mb-3 text-[11px] leading-relaxed text-muted-foreground">{def.description}</p>

        <div className="mb-3">
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Configuration</div>
          {Object.keys(defaults).length === 0 && <p className="text-[11px] text-muted-foreground">This node has no configuration.</p>}
          <div className="space-y-2">
            {Object.keys(defaults).map((key) => {
              const current = node.config[key] ?? defaults[key];
              const kind = fieldType(defaults[key]);
              return (
                <label key={key} className="block">
                  <span className="mb-0.5 block text-[11px] text-muted-foreground">{key}</span>
                  {kind === 'boolean' ? (
                    <input
                      type="checkbox"
                      checked={Boolean(current)}
                      onChange={(e) => setConfigValue(key, e.target.checked)}
                      className="h-4 w-4 accent-sky-500"
                    />
                  ) : kind === 'number' ? (
                    <input
                      type="number"
                      value={Number(current)}
                      onChange={(e) => setConfigValue(key, e.target.value === '' ? 0 : Number(e.target.value))}
                      className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-sky-400/50"
                    />
                  ) : kind === 'array' || kind === 'object' ? (
                    <textarea
                      value={JSON.stringify(current, null, 2)}
                      onChange={(e) => {
                        try {
                          setConfigValue(key, JSON.parse(e.target.value));
                        } catch {
                          /* keep previous valid value until the text parses */
                        }
                      }}
                      rows={kind === 'array' ? 2 : 4}
                      className="w-full resize-y rounded-md border border-white/10 bg-background/60 px-2 py-1 font-mono text-[11px] outline-none focus:border-sky-400/50"
                    />
                  ) : (
                    <input
                      value={String(current)}
                      onChange={(e) => setConfigValue(key, e.target.value)}
                      className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-sky-400/50"
                    />
                  )}
                </label>
              );
            })}
          </div>
          {configError && <p className="mt-2 text-[11px] text-rose-400">{configError}</p>}
          {lastError && <p className="mt-2 text-[11px] text-amber-400">{lastError}</p>}
        </div>

        <div className="mb-3">
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Inputs</div>
          {def.inputs.length === 0 ? <p className="text-[11px] text-muted-foreground">None</p> : def.inputs.map((p) => <PortRow key={p.id} port={p} direction="in" />)}
        </div>
        <div className="mb-3">
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Outputs</div>
          {def.outputs.length === 0 ? <p className="text-[11px] text-muted-foreground">None</p> : def.outputs.map((p) => <PortRow key={p.id} port={p} direction="out" />)}
        </div>

        {def.capabilities.length > 0 && (
          <div className="mb-3">
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Capabilities</div>
            <div className="flex flex-wrap gap-1">
              {def.capabilities.map((cap) => (
                <span key={cap} className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-muted-foreground">
                  {cap}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="mb-3">
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Allowed modes</div>
          <div className="flex flex-wrap gap-1">
            {def.allowedModes.map((mode) => (
              <span key={mode} className={cn('rounded-full px-2 py-0.5 text-[10px]', mode === 'live' ? 'bg-rose-500/15 text-rose-300' : 'bg-white/5 text-muted-foreground')}>
                {mode}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="border-t border-white/10 p-2">
        <button
          type="button"
          onClick={() => dispatch({ op: 'remove_node', nodeId: node.id })}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-300 hover:bg-rose-500/20"
        >
          <Trash2 size={12} /> Delete node
        </button>
      </div>
    </div>
  );
}
