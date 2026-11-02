'use client';

// ── Node test panel ──────────────────────────────────────────────────────────
// "Execute this step" — runs ONE node with explicit per-port inputs through the
// Python runtime. It never runs the graph, never persists a run, and never
// bypasses the node's timeout. Nodes with network/write/trading/model effects
// are refused by the runtime; they need an authorized run.

import { useEffect, useMemo, useState } from 'react';
import { Play } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  GraphRunApiError,
  testNode,
  type NodeRunRecord,
  type NodeTestResult,
} from '@/lib/graph-studio/execution-client';
import { portColor } from '@/lib/graph-studio/port-style';
import type { ExecutionMode, NodeDefinition, WorkflowNode } from '@/lib/graph-studio/types';

const MAX_PREFILL = 20_000;

function serialize(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return '{}';
  }
}

export function NodeTestPanel({
  node,
  definition,
  nodeRun,
  mode,
}: {
  node: WorkflowNode;
  definition: NodeDefinition;
  nodeRun?: NodeRunRecord;
  mode: ExecutionMode;
}) {
  const [text, setText] = useState('{}');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<NodeTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [allowNetwork, setAllowNetwork] = useState(false);

  useEffect(() => {
    const literals = node.inputValues ?? {};
    setText(Object.keys(literals).length > 0 ? serialize(literals) : '{}');
    setResult(null);
    setError(null);
    setAllowNetwork(false);
  }, [node.id, node.inputValues]);

  const lastInputs = nodeRun?.inputs ?? null;
  const lastSerialized = useMemo(
    () => (lastInputs && Object.keys(lastInputs).length > 0 ? serialize(lastInputs) : ''),
    [lastInputs],
  );
  const canUseLast = lastSerialized.length > 0 && lastSerialized.length <= MAX_PREFILL;

  const network = definition.sideEffects === 'network';
  const safe = definition.sideEffects === 'none' || definition.sideEffects === 'read';
  const canRun = safe || (network && allowNetwork);
  const isTrigger = definition.category === 'trigger';

  const currentInputs = (): { value: Record<string, unknown> } | { error: string } => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      return { error: 'Inputs must be valid JSON.' };
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { error: 'Inputs must be a JSON object keyed by input port id.' };
    }
    return { value: parsed as Record<string, unknown> };
  };

  const parsed = currentInputs();
  const provided = 'value' in parsed ? parsed.value : {};
  const missing = definition.inputs
    .filter((port) => !port.optional && !(port.id in provided))
    .map((port) => port.id);

  const run = async () => {
    const inputs = currentInputs();
    if ('error' in inputs) {
      setError(inputs.error);
      return;
    }
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await testNode({
        nodeType: definition.type,
        version: definition.version,
        config: node.config,
        inputs: inputs.value,
        mode,
        allowNetwork: network && allowNetwork,
      }));
    } catch (err) {
      setError(err instanceof GraphRunApiError ? err.message : err instanceof Error ? err.message : 'Test failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3 px-3 py-3">
      <div className="rounded-md border border-white/10 bg-white/[0.02] p-2">
        <p className="text-[11px] leading-relaxed text-foreground">
          Runs <span className="font-mono text-[10.5px]">{definition.type}</span> on its own with the
          inputs below — not the whole graph. Nothing is saved.
        </p>
        {isTrigger && (
          <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
            For a trigger, the output is the exact <span className="font-mono">Start</span> value it
            would emit on a run.
          </p>
        )}
        {!safe && !network && (
          <p className="mt-1 text-[10px] leading-relaxed text-amber-300">
            This node has the “{definition.sideEffects}” side effect. Per-node tests only allow
            none/read/confirmed-network effects — test it with an authorized run.
          </p>
        )}
        {network && (
          <label className="mt-1 flex items-start gap-1.5 text-[10px] leading-relaxed text-amber-200">
            <input
              type="checkbox"
              checked={allowNetwork}
              onChange={(event) => setAllowNetwork(event.target.checked)}
              className="mt-0.5"
            />
            <span>
              Allow this one test to make the real network request to{' '}
              <span className="font-mono">{String(node.config.url || '(configured url)')}</span>.
            </span>
          </label>
        )}
      </div>

      <section>
        <div className="mb-1 flex items-center justify-between">
          <span className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Inputs
          </span>
          {canUseLast && (
            <button
              type="button"
              onClick={() => setText(lastSerialized)}
              className="text-[9.5px] text-muted-foreground hover:text-foreground"
            >
              Use last run inputs
            </button>
          )}
        </div>
        {definition.inputs.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">None — this node runs from its config.</p>
        ) : (
          <>
            <div className="mb-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
              {definition.inputs.map((port) => (
                <span key={port.id} className="flex items-center gap-1 text-[9.5px] text-muted-foreground">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: portColor(port.type) }} />
                  <span className="font-mono">{port.id}</span>
                  <span>· {port.type}</span>
                  {!port.optional && <span className="text-rose-300">required</span>}
                </span>
              ))}
            </div>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={Math.min(12, Math.max(4, text.split('\n').length))}
              spellCheck={false}
              placeholder='{"symbol": "AAPL"}'
              className="w-full resize-y rounded-md border border-white/10 bg-background/60 px-2 py-1.5 font-mono text-[10.5px] text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-sky-400/40"
            />
            {'error' in parsed && <p className="mt-1 text-[10px] text-rose-300">{parsed.error}</p>}
            {missing.length > 0 && (
              <p className="mt-1 text-[10px] text-amber-300">Missing required: {missing.join(', ')}</p>
            )}
          </>
        )}
      </section>

      <button
        type="button"
        onClick={() => void run()}
        disabled={running || !canRun || missing.length > 0 || 'error' in parsed}
        title={!canRun ? 'Confirm the network request (or use an authorized run) to test this node' : 'Execute only this node'}
        className="flex w-full items-center justify-center gap-1.5 rounded-md border border-emerald-400/30 bg-emerald-500/10 px-2 py-1.5 text-[11px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-40"
      >
        <Play size={11} /> {running ? 'Testing…' : 'Test node'}
      </button>

      {error && (
        <p className="rounded-md border border-rose-500/25 bg-rose-500/10 px-2 py-1.5 text-[10.5px] text-rose-200">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[9.5px] text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            <span>succeeded</span>
            <span>· {result.durationMs} ms</span>
            <span>· {Object.keys(result.outputs).length} output(s)</span>
            {(result.firedControls?.length ?? 0) > 0 && (
              <span className="text-sky-300">· fired {result.firedControls?.join(', ')}</span>
            )}
          </div>
          <div>
            <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
              Output
            </div>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md border border-white/10 bg-black/30 p-2 font-mono text-[10px] leading-relaxed text-slate-300">
              {serialize(result.outputs)}
            </pre>
          </div>
          {result.logs.length > 0 && (
            <details>
              <summary className="cursor-pointer text-[9.5px] uppercase tracking-wider text-muted-foreground">
                Log ({result.logs.length})
              </summary>
              <div className="mt-1 space-y-0.5">
                {result.logs.map((line, index) => (
                  <div key={`${index}-${line}`} className="break-words font-mono text-[10px] text-muted-foreground">
                    {line}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
