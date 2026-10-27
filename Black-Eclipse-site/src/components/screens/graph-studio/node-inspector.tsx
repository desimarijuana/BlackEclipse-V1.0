'use client';

// ── Node inspector ───────────────────────────────────────────────────────────
// The node details surface: Parameters / Settings / Output. Fields are derived
// from the definition's `defaultConfig()` shape; every edit is dispatched as a
// validated patch. The Output tab is read-only and only shows what the runtime
// actually persisted for the selected run — never an optimistic value.

import { useEffect, useMemo, useState } from 'react';
import { Trash2, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { getNodeDefinition } from '@/lib/graph-studio/registry';
import { validateConfig } from '@/lib/graph-studio/validation';
import { portColor, sideEffectColor } from '@/lib/graph-studio/port-style';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { useWorkflowCatalog } from '@/lib/graph-studio/catalog-store';
import type { PortDef } from '@/lib/graph-studio/types';
import type { NodeRunRecord } from '@/lib/graph-studio/execution-client';
import { nodeIcon } from './node-icons';

type InspectorTab = 'parameters' | 'settings' | 'output';

function fieldType(value: unknown): 'boolean' | 'number' | 'array' | 'object' | 'string' {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (Array.isArray(value)) return 'array';
  if (value && typeof value === 'object') return 'object';
  return 'string';
}

function humanize(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/^./, (char) => char.toUpperCase());
}

function preview(value: unknown): string {
  if (value === undefined) return '—';
  try {
    const text = JSON.stringify(value, null, 2);
    return text.length > 4000 ? `${text.slice(0, 4000)}\n…` : text;
  } catch {
    return String(value);
  }
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

function JsonField({
  value, rows, className, onCommit,
}: {
  value: unknown;
  rows: number;
  className: string;
  onCommit: (value: unknown) => void;
}) {
  const serialized = JSON.stringify(value, null, 2);
  const [text, setText] = useState(serialized);
  useEffect(() => {
    setText(serialized);
  }, [serialized]);
  return (
    <textarea
      value={text}
      onChange={(event) => setText(event.target.value)}
      onBlur={() => {
        try {
          onCommit(JSON.parse(text));
        } catch {
          setText(serialized);
        }
      }}
      rows={rows}
      className={className}
    />
  );
}

function OutputTab({ nodeRun }: { nodeRun: NodeRunRecord | undefined }) {
  if (!nodeRun) {
    return (
      <div className="px-3 py-6 text-center text-[11.5px] leading-relaxed text-muted-foreground">
        No output captured for this node yet.<br />
        Save, then run the workflow to inspect its data.
      </div>
    );
  }
  const inputKeys = Object.keys(nodeRun.inputs ?? {});
  const outputKeys = Object.keys(nodeRun.outputs ?? {});
  return (
    <div className="space-y-3 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
        <span className={cn(
          'rounded-full border px-2 py-0.5',
          nodeRun.status === 'failed'
            ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
            : nodeRun.status === 'succeeded'
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
              : 'border-white/10 bg-white/5',
        )}>
          {nodeRun.status}
        </span>
        {typeof nodeRun.durationMs === 'number' && <span>{nodeRun.durationMs} ms</span>}
        {nodeRun.attempt > 1 && <span className="text-amber-300">attempt {nodeRun.attempt}</span>}
        {nodeRun.resumable && <span className="text-emerald-300/80">checkpoint saved</span>}
      </div>
      {nodeRun.error && (
        <p className="rounded-md border border-rose-500/25 bg-rose-500/10 px-2 py-1.5 text-[10.5px] text-rose-200">
          {nodeRun.errorCode ? `${nodeRun.errorCode}: ` : ''}
          {nodeRun.error}
        </p>
      )}
      <section>
        <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Inputs</div>
        {inputKeys.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">No values captured.</p>
        ) : (
          inputKeys.map((key) => (
            <div key={key} className="mb-1">
              <div className="text-[10px] text-muted-foreground">{key}</div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded border border-white/10 bg-black/20 p-1.5 font-mono text-[10px] text-slate-300">
                {preview(nodeRun.inputs[key])}
              </pre>
            </div>
          ))
        )}
      </section>
      <section>
        <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Outputs</div>
        {outputKeys.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">No values captured.</p>
        ) : (
          outputKeys.map((key) => (
            <div key={key} className="mb-1">
              <div className="text-[10px] text-muted-foreground">{key}</div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded border border-white/10 bg-black/20 p-1.5 font-mono text-[10px] text-slate-300">
                {preview(nodeRun.outputs[key])}
              </pre>
            </div>
          ))
        )}
      </section>
    </div>
  );
}

export function NodeInspector({ onClose }: { onClose?: () => void }) {
  const ir = useGraphEditor((s) => s.ir);
  const selection = useGraphEditor((s) => s.selection);
  const dispatch = useGraphEditor((s) => s.dispatch);
  const lastError = useGraphEditor((s) => s.lastError);
  const run = useGraphEditor((s) => s.run);
  const workflows = useWorkflowCatalog((s) => s.summaries);
  const refreshWorkflows = useWorkflowCatalog((s) => s.refresh);
  const currentWorkflowId = useGraphEditor((s) => s.workflowId);
  const [tab, setTab] = useState<InspectorTab>('parameters');

  useEffect(() => {
    if (workflows.length === 0) void refreshWorkflows();
  }, [workflows.length, refreshWorkflows]);

  const node = ir && selection.nodeIds.length === 1 ? ir.nodes.find((n) => n.id === selection.nodeIds[0]) : undefined;

  useEffect(() => {
    setTab('parameters');
  }, [node?.id]);

  const nodeRun = useMemo(
    () => (run && node ? run.nodeRuns?.find((item) => item.nodeId === node.id) : undefined),
    [run, node],
  );

  if (!node) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <p className="text-[12px] text-muted-foreground">Select a node to configure it.</p>
        <p className="mt-1 text-[10.5px] text-muted-foreground/70">Press Tab on the canvas to add a step.</p>
      </div>
    );
  }
  const def = getNodeDefinition(node.type, node.version);
  if (!def) {
    return <div className="px-3 py-4 text-[12px] text-rose-400">Unknown node type “{node.type}”.</div>;
  }

  const Icon = nodeIcon(def.icon, def.category);
  const accent = sideEffectColor(def.sideEffects);
  const configError = validateConfig(def, node.config);
  const defaults = def.defaultConfig();
  const isSubworkflow = node.type === 'flow.subworkflow';
  const configKeys = Object.keys(defaults).filter(
    (key) => !(isSubworkflow && (key === 'workflowId' || key === 'version')),
  );
  const selectedWorkflow = workflows.find((item) => item.id === node.config.workflowId);

  const setConfigValue = (key: string, value: unknown) => {
    dispatch({ op: 'update_node_config', nodeId: node.id, config: { ...node.config, [key]: value } });
  };

  const tabs: [InspectorTab, string][] = [
    ['parameters', 'Parameters'],
    ['settings', 'Settings'],
    ['output', nodeRun ? `Output${nodeRun.status === 'failed' ? ' · error' : ''}` : 'Output'],
  ];

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start gap-2 border-b border-white/10 px-3 py-2.5">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg" style={{ background: `${accent}1f`, color: accent }}>
          <Icon size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <input
            value={node.label ?? ''}
            placeholder={def.label}
            onChange={(event) => dispatch({ op: 'update_node_label', nodeId: node.id, label: event.target.value || undefined })}
            className="w-full rounded-md border border-transparent bg-transparent px-1 py-0.5 text-[13px] font-semibold text-foreground outline-none hover:border-white/10 focus:border-primary/50"
          />
          <div className="mt-1 flex items-center gap-1.5 px-1 text-[10px] text-muted-foreground">
            <span className="truncate">{def.label} · v{node.version}</span>
            <span className="ml-auto shrink-0 rounded-full px-1.5 py-0.5" style={{ background: `${accent}1f`, color: accent }}>
              {def.sideEffects}
            </span>
          </div>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} title="Close inspector" className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground">
            <X size={13} />
          </button>
        )}
      </div>

      <div className="flex shrink-0 border-b border-white/10 px-1.5">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              'border-b-2 px-2.5 py-1.5 text-[11px] transition-colors',
              tab === id
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === 'parameters' && (
          <div className="px-3 py-3">
            {isSubworkflow && (
              <div className="mb-3 rounded-md border border-white/10 bg-white/[0.02] p-2">
                <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Pinned subworkflow</div>
                <select
                  value={String(node.config.workflowId ?? '')}
                  onChange={(event) => {
                    const chosen = workflows.find((item) => item.id === event.target.value);
                    dispatch({
                      op: 'update_node_config',
                      nodeId: node.id,
                      config: { ...node.config, workflowId: event.target.value, version: chosen?.currentVersion ?? 1 },
                    });
                  }}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
                >
                  <option value="">Select a saved workflow…</option>
                  {workflows.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} (v{item.currentVersion})
                    </option>
                  ))}
                </select>
                <label className="mt-1.5 block">
                  <span className="mb-0.5 block text-[10.5px] text-muted-foreground">Pinned version</span>
                  <input
                    type="number"
                    min={1}
                    max={selectedWorkflow?.currentVersion ?? 1_000_000}
                    value={Number(node.config.version ?? 1)}
                    onChange={(event) => setConfigValue('version', Math.max(1, Number(event.target.value) || 1))}
                    className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
                  />
                </label>
                {workflows.length === 0 && (
                  <p className="mt-1 text-[10px] text-muted-foreground">No saved workflows yet. Save a child workflow, then pin it here.</p>
                )}
                {selectedWorkflow && selectedWorkflow.id === currentWorkflowId && (
                  <p className="mt-1 text-[10px] text-amber-300">A workflow cannot call itself; the compiler will refuse this cycle.</p>
                )}
              </div>
            )}

            {configKeys.length === 0 && !isSubworkflow && (
              <p className="text-[11.5px] text-muted-foreground">This node has no configuration.</p>
            )}

            <div className="space-y-2.5">
              {configKeys.map((key) => {
                const current = node.config[key] ?? defaults[key];
                const kind = fieldType(defaults[key]);
                const fieldClass = 'w-full rounded-md border border-white/10 bg-background/60 px-2 py-1.5 text-[12px] outline-none focus:border-primary/50';
                return (
                  <label key={key} className="block">
                    <span className="mb-1 block text-[10.5px] text-muted-foreground">{humanize(key)}</span>
                    {kind === 'boolean' ? (
                      <span className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={Boolean(current)}
                          onChange={(event) => setConfigValue(key, event.target.checked)}
                          className="h-4 w-4 accent-primary"
                        />
                        <span className="text-[11px] text-muted-foreground">{Boolean(current) ? 'Enabled' : 'Disabled'}</span>
                      </span>
                    ) : kind === 'number' ? (
                      <input
                        type="number"
                        value={Number(current)}
                        onChange={(event) => setConfigValue(key, event.target.value === '' ? 0 : Number(event.target.value))}
                        className={fieldClass}
                      />
                    ) : kind === 'array' || kind === 'object' ? (
                      <JsonField
                        value={current}
                        rows={kind === 'array' ? 3 : 5}
                        className={cn(fieldClass, 'resize-y font-mono text-[11px]')}
                        onCommit={(next) => setConfigValue(key, next)}
                      />
                    ) : (
                      <input
                        value={String(current)}
                        onChange={(event) => setConfigValue(key, event.target.value)}
                        className={fieldClass}
                      />
                    )}
                  </label>
                );
              })}
            </div>
            {configError && <p className="mt-2 text-[11px] text-rose-400">{configError}</p>}
            {lastError && <p className="mt-2 text-[11px] text-amber-400">{lastError}</p>}
          </div>
        )}

        {tab === 'settings' && (
          <div className="space-y-4 px-3 py-3">
            <p className="text-[11px] leading-relaxed text-muted-foreground">{def.description}</p>
            <section>
              <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Inputs</div>
              {def.inputs.length === 0 ? <p className="text-[11px] text-muted-foreground">None</p> : def.inputs.map((port) => <PortRow key={port.id} port={port} direction="in" />)}
            </section>
            <section>
              <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Outputs</div>
              {def.outputs.length === 0 ? <p className="text-[11px] text-muted-foreground">None</p> : def.outputs.map((port) => <PortRow key={port.id} port={port} direction="out" />)}
            </section>
            {def.capabilities.length > 0 && (
              <section>
                <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Capabilities</div>
                <div className="flex flex-wrap gap-1">
                  {def.capabilities.map((capability) => (
                    <span key={capability} className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-muted-foreground">
                      {capability}
                    </span>
                  ))}
                </div>
              </section>
            )}
            <section>
              <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Allowed modes</div>
              <div className="flex flex-wrap gap-1">
                {def.allowedModes.map((mode) => (
                  <span key={mode} className={cn('rounded-full px-2 py-0.5 text-[10px]', mode === 'live' ? 'bg-rose-500/15 text-rose-300' : 'bg-white/5 text-muted-foreground')}>
                    {mode}
                  </span>
                ))}
              </div>
            </section>
            <section>
              <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Node id</div>
              <p className="break-all font-mono text-[10px] text-muted-foreground">{node.id}</p>
            </section>
          </div>
        )}

        {tab === 'output' && <OutputTab nodeRun={nodeRun} />}
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
