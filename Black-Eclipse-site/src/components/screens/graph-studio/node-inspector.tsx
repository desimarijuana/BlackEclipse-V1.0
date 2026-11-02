'use client';

// ── Node inspector ───────────────────────────────────────────────────────────
// The node details surface: Parameters / Settings / Output. Fields are derived
// from the definition's `defaultConfig()` shape; every edit is dispatched as a
// validated patch. The Output tab is read-only and only shows what the runtime
// actually persisted for the selected run — never an optimistic value.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Trash2, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { getNodeDefinition } from '@/lib/graph-studio/registry';
import { fieldsFor } from '@/lib/graph-studio/config-fields';
import { exampleFor } from '@/lib/graph-studio/node-examples';
import { visiblePorts } from '@/lib/graph-studio/node-ports';
import { validateConfig } from '@/lib/graph-studio/validation';
import { portColor, sideEffectColor } from '@/lib/graph-studio/port-style';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { useWorkflowCatalog } from '@/lib/graph-studio/catalog-store';
import {
  BUILT_IN_AGENTS,
  listAgentPresets,
  listBuiltInAgents,
  type AgentPresetSummary,
} from '@/lib/agent-presets/client';
import {
  listBrokerConnections,
  listTradingMandates,
  type BrokerConnection,
  type TradingMandate,
} from '@/lib/harness/trading-client';
import type { PortDef } from '@/lib/graph-studio/types';
import type { DatasetSummary, NodeRunRecord } from '@/lib/graph-studio/execution-client';
import { listDatasets } from '@/lib/graph-studio/execution-client';
import { nodeIcon } from './node-icons';
import { ConfigField } from './config-field';
import { PortValueEditor } from './port-value-editor';
import { NodeTestPanel } from './node-test-panel';
import { SchedulePanel } from './schedule-panel';
import { WebhookPanel } from './webhook-panel';

type InspectorTab = 'parameters' | 'test' | 'schedule' | 'webhook' | 'settings' | 'output';

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
  const control = port.kind === 'control';
  return (
    <div className="flex items-center gap-2 py-0.5 text-[11px]">
      <span
        className={cn('h-2 w-2 shrink-0', control ? 'rounded-[2px]' : 'rounded-full')}
        style={{ background: portColor(port.type) }}
      />
      <span className="truncate text-foreground">{port.name}</span>
      <span className="ml-auto shrink-0 text-muted-foreground">
        {direction === 'in' ? '←' : '→'} {control ? 'control' : port.type}
        {port.optional ? ' · optional' : ''}
      </span>
    </div>
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
  const [jsonOpen, setJsonOpen] = useState(false);
  const [jsonDraft, setJsonDraft] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [paramQuery, setParamQuery] = useState('');
  const [agentPresets, setAgentPresets] = useState<AgentPresetSummary[]>([]);
  const [builtInAgents, setBuiltInAgents] = useState<Array<{ id: string; name: string }>>(
    [...BUILT_IN_AGENTS],
  );
  const [agentPresetsError, setAgentPresetsError] = useState<string | null>(null);
  const [brokerConnections, setBrokerConnections] = useState<BrokerConnection[]>([]);
  const [brokerMandates, setBrokerMandates] = useState<TradingMandate[]>([]);
  const [brokerError, setBrokerError] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [datasetsLoading, setDatasetsLoading] = useState(false);

  useEffect(() => {
    if (workflows.length === 0) void refreshWorkflows();
  }, [workflows.length, refreshWorkflows]);

  const node = ir && selection.nodeIds.length === 1 ? ir.nodes.find((n) => n.id === selection.nodeIds[0]) : undefined;
  const isAgentNode =
    node?.type === 'agent.research' || node?.type === 'agent.delegate';
  const isBrokerNode = Boolean(node?.type.startsWith('trading.broker_'));
  const isDatasetLoad = node?.type === 'data.dataset.load';

  const loadDatasets = useCallback(async () => {
    setDatasetsLoading(true);
    try {
      setDatasets(await listDatasets());
      setDatasetsError(null);
    } catch (err) {
      setDatasetsError(err instanceof Error ? err.message : 'datasets unavailable');
    } finally {
      setDatasetsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isDatasetLoad) return;
    void loadDatasets();
  }, [isDatasetLoad, loadDatasets]);

  useEffect(() => {
    if (!isAgentNode) return;
    let live = true;
    void Promise.all([listAgentPresets(), listBuiltInAgents()])
      .then(([items, builtins]) => {
        if (!live) return;
        setAgentPresets(items);
        if (builtins.length > 0) setBuiltInAgents(builtins);
        setAgentPresetsError(null);
      })
      .catch((err) => { if (live) setAgentPresetsError(err instanceof Error ? err.message : 'presets unavailable'); });
    return () => { live = false; };
  }, [isAgentNode]);

  useEffect(() => {
    if (!isBrokerNode) return;
    let live = true;
    void listBrokerConnections()
      .then((items) => { if (live) { setBrokerConnections(items); setBrokerError(null); } })
      .catch((err) => { if (live) setBrokerError(err instanceof Error ? err.message : 'connections unavailable'); });
    return () => { live = false; };
  }, [isBrokerNode]);

  const brokerConnectionId = String(node?.config.connectionId ?? '');
  useEffect(() => {
    if (!isBrokerNode || !brokerConnectionId) {
      setBrokerMandates([]);
      return;
    }
    let live = true;
    void listTradingMandates(brokerConnectionId)
      .then((items) => {
        if (!live) return;
        setBrokerMandates(items.filter((item) => !item.revokedAt && item.remainingOrders > 0));
      })
      .catch(() => { if (live) setBrokerMandates([]); });
    return () => { live = false; };
  }, [isBrokerNode, brokerConnectionId]);

  useEffect(() => {
    setTab(
      node?.type === 'trigger.schedule'
        ? 'schedule'
        : node?.type === 'trigger.webhook'
          ? 'webhook'
          : 'parameters',
    );
    setJsonOpen(false);
    setJsonError(null);
    setParamQuery('');
  }, [node?.id, node?.type]);

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
  const isSubworkflow =
    node.type === 'flow.subworkflow'
    || node.type === 'flow.for_each'
    || node.type === 'flow.repeat'
    || node.type === 'flow.while';
  const fields = fieldsFor(def).filter((field) => {
    if (isSubworkflow && (field.key === 'workflowId' || field.key === 'version')) return false;
    if (isAgentNode && (field.key === 'agent' || field.key === 'agentVersion')) return false;
    if (isBrokerNode && (field.key === 'connectionId' || field.key === 'mandateId')) return false;
    return true;
  });
  const currentAgentId = String(node.config.agent ?? 'eclipse-agent');

  const normalizedQuery = paramQuery.trim().toLowerCase();
  const visibleFields = normalizedQuery
    ? fields.filter((field) =>
        `${field.label} ${field.key} ${field.help ?? ''}`.toLowerCase().includes(normalizedQuery),
      )
    : fields;
  const fieldGroups = visibleFields.reduce<Array<{ name: string; fields: typeof fields }>>(
    (groups, field) => {
      const name = field.group ?? 'Parameters';
      const existing = groups.find((group) => group.name === name);
      if (existing) existing.fields.push(field);
      else groups.push({ name, fields: [field] });
      return groups;
    },
    [],
  );
  const selectedWorkflow = workflows.find((item) => item.id === node.config.workflowId);
  const wiredInputs = new Set(
    (ir?.edges ?? [])
      .filter((edge) => edge.target === node.id)
      .map((edge) => edge.targetHandle),
  );
  const wiredOutputs = (ir?.edges ?? [])
    .filter((edge) => edge.source === node.id)
    .map((edge) => edge.sourceHandle);
  // The inspector must agree with the card: a Switch lists only the cases it has.
  const shownPorts = visiblePorts(def, node, wiredOutputs);
  const dataInputs = shownPorts.inputs.filter((port) => port.kind !== 'control');

  const openJson = () => {
    setJsonDraft(JSON.stringify(node.config, null, 2));
    setJsonError(null);
    setJsonOpen(true);
  };

  const applyJson = () => {
    try {
      const parsed = JSON.parse(jsonDraft) as unknown;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setJsonError('Config must be a JSON object.');
        return;
      }
      dispatch({
        op: 'update_node_config',
        nodeId: node.id,
        config: parsed as Record<string, unknown>,
      });
      setJsonError(null);
      setJsonOpen(false);
    } catch (err) {
      setJsonError(err instanceof Error ? err.message : 'Invalid JSON');
    }
  };

  const setConfigValue = (key: string, value: unknown) => {
    dispatch(
      { op: 'update_node_config', nodeId: node.id, config: { ...node.config, [key]: value } },
      { coalesceKey: `config:${node.id}:${key}` },
    );
  };

  const tabs: [InspectorTab, string][] = [];
  if (node.type === 'trigger.schedule') tabs.push(['schedule', 'Schedule']);
  if (node.type === 'trigger.webhook') tabs.push(['webhook', 'Webhook']);
  tabs.push(
    ['parameters', 'Parameters'],
    ['test', 'Test'],
    ['settings', 'Settings'],
    ['output', nodeRun ? `Output${nodeRun.status === 'failed' ? ' · error' : ''}` : 'Output'],
  );

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
            onChange={(event) => dispatch(
              { op: 'update_node_label', nodeId: node.id, label: event.target.value || undefined },
              { coalesceKey: `label:${node.id}` },
            )}
            className="w-full rounded-md border border-transparent bg-transparent px-1 py-0.5 text-[13px] font-semibold text-foreground outline-none hover:border-white/10 focus:border-primary/50"
          />
          <div className="mt-1 flex items-center gap-1.5 px-1 text-[10px] text-muted-foreground">
            <span className="truncate">{def.label} · v{node.version}</span>
            <span className="ml-auto shrink-0 rounded-full px-1.5 py-0.5" style={{ background: `${accent}1f`, color: accent }}>
              {def.sideEffects}
            </span>
          </div>
          <p className="mt-1 px-1 text-[10px] leading-snug text-muted-foreground/80">{def.description}</p>
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
            <div className="mb-3 rounded-md border border-white/10 bg-white/[0.02] p-2">
              <p className="text-[11px] leading-relaxed text-foreground">{def.description}</p>
              {def.docs && (
                <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">{def.docs}</p>
              )}
            </div>
            {isDatasetLoad && (
              <div className="mb-3 rounded-md border border-white/10 bg-white/[0.02] p-2">
                <div className="mb-1 flex items-center justify-between">
                  <div className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Saved datasets
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadDatasets()}
                    className="text-[9.5px] text-muted-foreground hover:text-foreground"
                  >
                    {datasetsLoading ? 'Loading…' : 'Refresh'}
                  </button>
                </div>
                <select
                  value={String(node.config.ref ?? '')}
                  onChange={(event) => setConfigValue('ref', event.target.value)}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
                >
                  <option value="">Select a saved dataset…</option>
                  {datasets.map((dataset) => (
                    <option key={dataset.ref} value={dataset.ref}>
                      {dataset.name} · {dataset.valueType}
                      {typeof dataset.rows === 'number' ? ` · ${dataset.rows} row(s)` : ''} · {dataset.bytes} B
                    </option>
                  ))}
                </select>
                {datasets.length === 0 && !datasetsLoading && !datasetsError && (
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    No saved datasets yet. Run a Save dataset node first, then refresh.
                  </p>
                )}
                {datasetsError && <p className="mt-1 text-[10px] text-amber-300">{datasetsError}</p>}
                {node.config.ref ? (
                  <div className="mt-1 flex items-center gap-2 text-[9.5px] text-muted-foreground">
                    <span className="break-all font-mono">{String(node.config.ref)}</span>
                    <button
                      type="button"
                      onClick={() => setConfigValue('ref', '')}
                      className="ml-auto shrink-0 hover:text-foreground"
                    >
                      Clear
                    </button>
                  </div>
                ) : (
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Or paste a ref below. A wired Ref port overrides this selection.
                  </p>
                )}
              </div>
            )}
            {dataInputs.length > 0 && (
              <div className="mb-3 rounded-md border border-white/10 bg-white/[0.02] p-2">
                <div className="mb-1 flex items-center justify-between text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <span>Inputs</span>
                  <span className="font-normal normal-case tracking-normal text-muted-foreground/70">
                    wire wins
                  </span>
                </div>
                <p className="mb-2 text-[10px] leading-snug text-muted-foreground/70">
                  Give an unwired input a literal value here; a connected wire overrides it.
                </p>
                <div className="space-y-2">
                  {dataInputs.map((port) => (
                    <div key={port.id}>
                      <div className="mb-1 flex items-center gap-1.5 text-[10.5px]">
                        <span className="h-1.5 w-1.5 rounded-full" style={{ background: portColor(port.type) }} />
                        <span className="text-foreground">{port.name}</span>
                        <span className="text-muted-foreground">· {port.type}</span>
                        {!port.optional && (
                          <span className="text-rose-300/80">required</span>
                        )}
                        {wiredInputs.has(port.id) && (
                          <span className="ml-auto text-muted-foreground/70">wired</span>
                        )}
                      </div>
                      <PortValueEditor
                        port={port}
                        value={node.inputValues?.[port.id]}
                        wired={wiredInputs.has(port.id)}
                        onChange={(value) => dispatch(
                          { op: 'update_node_input_value', nodeId: node.id, portId: port.id, value },
                          { coalesceKey: `input:${node.id}:${port.id}` },
                        )}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
            {isBrokerNode && (
              <div className="mb-3 rounded-md border border-white/10 bg-white/[0.02] p-2">
                <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Broker connection
                </div>
                <select
                  value={brokerConnectionId}
                  onChange={(event) => {
                    const connection = brokerConnections.find((item) => item.id === event.target.value);
                    dispatch({
                      op: 'update_node_config',
                      nodeId: node.id,
                      config: {
                        ...node.config,
                        connectionId: event.target.value,
                        ...(connection?.mode === 'live' ? {} : { mandateId: '' }),
                      },
                    });
                  }}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
                >
                  <option value="">Select a saved connection…</option>
                  {brokerConnections.map((connection) => (
                    <option key={connection.id} value={connection.id}>
                      {connection.label} ({connection.mode})
                    </option>
                  ))}
                </select>
                {brokerError && <p className="mt-1 text-[10px] text-amber-300">{brokerError}</p>}
                {node.type === 'trading.broker_order' && (
                  <>
                    <div className="mb-1 mt-2 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Mandate
                    </div>
                    <select
                      value={String(node.config.mandateId ?? '')}
                      onChange={(event) => setConfigValue('mandateId', event.target.value)}
                      className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
                    >
                      <option value="">Select an active mandate…</option>
                      {brokerMandates.map((mandate) => (
                        <option key={mandate.id} value={mandate.id}>
                          {mandate.mode} · {mandate.symbols.join(', ')} · {mandate.remainingOrders} left
                        </option>
                      ))}
                    </select>
                  </>
                )}
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Live orders require the connection to be armed and a workflow-pinned live mandate.
                  Manage them in Settings › Broker connection.
                </p>
              </div>
            )}
            {isAgentNode && (
              <div className="mb-3 rounded-md border border-white/10 bg-white/[0.02] p-2">
                <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Agent preset
                </div>
                <select
                  value={currentAgentId}
                  onChange={(event) => {
                    const id = event.target.value;
                    const custom = agentPresets.find((item) => item.id === id);
                    dispatch({
                      op: 'update_node_config',
                      nodeId: node.id,
                      config: {
                        ...node.config,
                        agent: id,
                        // Pin a custom preset's current version; built-ins are
                        // code-resolved and use 0 (= latest).
                        agentVersion: custom ? custom.version : 0,
                      },
                    });
                  }}
                  className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
                >
                  <optgroup label="Built-in">
                    {builtInAgents.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </optgroup>
                  {agentPresets.length > 0 && (
                    <optgroup label="Custom">
                      {agentPresets.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name} (v{item.version})
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
                {agentPresetsError && (
                  <p className="mt-1 text-[10px] text-amber-300">{agentPresetsError}</p>
                )}
                {Number(node.config.agentVersion ?? 0) > 0 && (
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Pinned to v{Number(node.config.agentVersion)}. Editing the preset creates a new version;
                    this node keeps the pinned snapshot.
                  </p>
                )}
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Manage presets in Settings › Agents.
                </p>
              </div>
            )}
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

            {fields.length === 0 && !isSubworkflow && (
              <p className="text-[11.5px] text-muted-foreground">This node has no configuration.</p>
            )}

            {fields.length > 6 && (
              <input
                value={paramQuery}
                onChange={(event) => setParamQuery(event.target.value)}
                placeholder={`Search ${fields.length} parameters…`}
                className="mb-3 w-full rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[11px] outline-none placeholder:text-muted-foreground/60 focus:border-primary/50"
              />
            )}

            <div className="space-y-4">
              {fieldGroups.map((group) => (
                <div key={group.name} className="space-y-2.5">
                  {fieldGroups.length > 1 && (
                    <div className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {group.name}
                    </div>
                  )}
                  {group.fields.map((field) => {
                    const current = node.config[field.key] ?? defaults[field.key];
                    const changed = JSON.stringify(current) !== JSON.stringify(defaults[field.key]);
                    return (
                      <div key={field.key}>
                        <ConfigField
                          field={field}
                          value={current}
                          variant="panel"
                          onCommit={(next) => setConfigValue(field.key, next)}
                        />
                        {changed && (
                          <button
                            type="button"
                            onClick={() => setConfigValue(field.key, defaults[field.key])}
                            className="mt-0.5 text-[9.5px] text-muted-foreground hover:text-foreground"
                          >
                            Reset to default
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
              {visibleFields.length === 0 && fields.length > 0 && (
                <p className="text-[11px] text-muted-foreground">No parameters match “{paramQuery}”.</p>
              )}
            </div>
            {configError && <p className="mt-2 text-[11px] text-rose-400">{configError}</p>}
            {lastError && <p className="mt-2 text-[11px] text-amber-400">{lastError}</p>}

            <div className="mt-3 border-t border-white/10 pt-2">
              {!jsonOpen ? (
                <button
                  type="button"
                  onClick={openJson}
                  className="text-[10.5px] text-muted-foreground hover:text-foreground"
                >
                  Advanced: edit config as JSON
                </button>
              ) : (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>Advanced JSON</span>
                    <button type="button" onClick={() => setJsonOpen(false)} className="hover:text-foreground">
                      Close
                    </button>
                  </div>
                  <textarea
                    value={jsonDraft}
                    onChange={(event) => setJsonDraft(event.target.value)}
                    rows={10}
                    spellCheck={false}
                    className="w-full rounded-md border border-white/10 bg-background/60 px-2 py-1.5 font-mono text-[11px] text-foreground outline-none focus:border-primary/50"
                  />
                  {jsonError && <p className="text-[10.5px] text-rose-400">{jsonError}</p>}
                  <button
                    type="button"
                    onClick={applyJson}
                    className="rounded-md border border-primary/40 bg-primary/10 px-2 py-1 text-[10.5px] text-primary hover:bg-primary/20"
                  >
                    Apply JSON
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 'settings' && (
          <div className="space-y-4 px-3 py-3">
            <p className="text-[11px] leading-relaxed text-muted-foreground">{def.description}</p>
            {def.docs && <p className="text-[10px] leading-relaxed text-muted-foreground/70">{def.docs}</p>}
            {exampleFor(def.type) && (
              <section>
                <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Example</div>
                <p className="rounded-md border border-white/10 bg-background/50 px-2 py-1.5 font-mono text-[10px] leading-relaxed text-muted-foreground">
                  {exampleFor(def.type)}
                </p>
              </section>
            )}
            <section>
              <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Notes</div>
              <textarea
                value={node.notes ?? ''}
                onChange={(event) => dispatch(
                  { op: 'update_node_notes', nodeId: node.id, notes: event.target.value },
                  { coalesceKey: `notes:${node.id}` },
                )}
                rows={4}
                placeholder="Why this step exists, assumptions, or a reminder for the operator…"
                className="w-full resize-y rounded-md border border-white/10 bg-background/60 px-2 py-1.5 text-[11px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/50"
              />
              <p className="mt-1 text-[10px] text-muted-foreground/70">Saved with the workflow; never executed.</p>
            </section>
            <section>
              <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Inputs</div>
              {shownPorts.inputs.length === 0 ? <p className="text-[11px] text-muted-foreground">None</p> : shownPorts.inputs.map((port) => <PortRow key={port.id} port={port} direction="in" />)}
            </section>
            <section>
              <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">Outputs</div>
              {shownPorts.outputs.length === 0 ? <p className="text-[11px] text-muted-foreground">None</p> : shownPorts.outputs.map((port) => <PortRow key={port.id} port={port} direction="out" />)}
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

        {tab === 'schedule' && (
          <SchedulePanel workflowId={currentWorkflowId} nodeId={node.id} />
        )}

        {tab === 'webhook' && (
          <WebhookPanel workflowId={currentWorkflowId} nodeId={node.id} />
        )}

        {tab === 'test' && (
          <NodeTestPanel
            node={node}
            definition={def}
            nodeRun={nodeRun}
            mode={ir?.settings.executionMode ?? 'research'}
          />
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
