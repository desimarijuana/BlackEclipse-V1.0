'use client';

// ── Graph Studio — workspace ─────────────────────────────────────────────────
// The canvas surface of the dedicated Graph Studio mode. The workflow browser
// and node library live in the MODE PANEL (the left sidebar, where Bots lists
// bots) so this screen is just the graph, its inspector and its run console.
//
// The shell hides the top bar in this tab (no header), matching the mode's
// full-bleed engineering workspace.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Check, GitBranch, LayoutGrid, Play, Plus, Redo2, Save, ScanSearch, Undo2, X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { useWorkflowCatalog } from '@/lib/graph-studio/catalog-store';
import { WORKFLOW_TEMPLATES } from '@/lib/graph-studio/templates';
import { createWorkflow, saveWorkflow, WorkflowApiError } from '@/lib/graph-studio/persistence-client';
import {
  cancelGraphRun, getGraphRun, isTerminal, isRunTerminalEvent, nodeStatusFromEvent,
  openGraphRunStream, startWorkflowRun, GraphRunApiError,
} from '@/lib/graph-studio/execution-client';
import type { ExecutionMode } from '@/lib/graph-studio/types';
import { GraphCanvas } from './graph-canvas';
import { NodeInspector } from './node-inspector';
import { ValidationPanel } from './validation-panel';
import { RunPanel } from './run-panel';
import { ScheduleList } from './schedule-list';
import { HistoryPanel } from './history-panel';

type RightTab = 'inspect' | 'issues' | 'run' | 'history';
const MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

export function GraphStudioScreen() {
  const ir = useGraphEditor((s) => s.ir);
  const workflowId = useGraphEditor((s) => s.workflowId);
  const baseVersion = useGraphEditor((s) => s.baseVersion);
  const dirty = useGraphEditor((s) => s.dirty);
  const diagnostics = useGraphEditor((s) => s.diagnostics);
  const load = useGraphEditor((s) => s.load);
  const dispatch = useGraphEditor((s) => s.dispatch);
  const undo = useGraphEditor((s) => s.undo);
  const redo = useGraphEditor((s) => s.redo);
  const applyAutoLayout = useGraphEditor((s) => s.applyAutoLayout);
  const markSaved = useGraphEditor((s) => s.markSaved);
  const setRun = useGraphEditor((s) => s.setRun);
  const run = useGraphEditor((s) => s.run);
  const past = useGraphEditor((s) => s.past.length);
  const future = useGraphEditor((s) => s.future.length);

  const refreshCatalog = useWorkflowCatalog((s) => s.refresh);
  const createFromTemplate = useWorkflowCatalog((s) => s.createFromTemplate);
  const summaries = useWorkflowCatalog((s) => s.summaries);
  const currentVersion = useMemo(
    () => summaries.find((summary) => summary.id === workflowId)?.currentVersion ?? baseVersion,
    [summaries, workflowId, baseVersion],
  );

  const fitRef = useRef<(() => void) | null>(null);
  const streamRef = useRef<(() => void) | null>(null);

  const [rightTab, setRightTab] = useState<RightTab>('inspect');
  const [busy, setBusy] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const pollingRef = useRef(false);

  const errorCount = useMemo(() => diagnostics.filter((d) => d.severity === 'error').length, [diagnostics]);

  useEffect(() => {
    void refreshCatalog();
  }, [refreshCatalog]);

  const save = useCallback(async () => {
    const current = useGraphEditor.getState().ir;
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      if (workflowId) {
        const record = await saveWorkflow(workflowId, current);
        markSaved(record.version, record.contentHash);
        setNotice(`Saved as v${record.version}`);
        void refreshCatalog();
      } else {
        const record = await createWorkflow({ name: current.name, description: current.description, ir: current });
        load(record.ir, { workflowId: record.id, baseVersion: record.version, contentHash: record.contentHash });
        void refreshCatalog();
        setNotice('Created');
      }
      setTimeout(() => setNotice(null), 2500);
    } catch (err) {
      if (err instanceof WorkflowApiError) setError(err.message);
      else setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setBusy(false);
    }
  }, [workflowId, load, markSaved, refreshCatalog]);

  // Fallback poll for environments where SSE is unavailable/disconnects. The
  // runtime owns the run; this only reflects what it reports.
  const pollUntilDone = useCallback(
    async (runId: string) => {
      pollingRef.current = true;
      const deadline = Date.now() + 10 * 60 * 1000;
      try {
        while (pollingRef.current && Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, 700));
          const record = await getGraphRun(runId);
          setRun(record);
          if (isTerminal(record.status)) return;
        }
      } catch (err) {
        if (err instanceof GraphRunApiError) setError(err.message);
      } finally {
        pollingRef.current = false;
      }
    },
    [setRun],
  );

  const refreshRun = useCallback(
    async (runId: string) => {
      const close = streamRef.current;
      streamRef.current = null;
      close?.();
      pollingRef.current = false;
      try {
        setRun(await getGraphRun(runId));
      } catch (err) {
        if (err instanceof GraphRunApiError) setError(err.message);
      }
    },
    [setRun],
  );

  // Live run stream: replay + tail the runtime's persisted graph events. The
  // run record is still fetched once at a terminal event so node outputs,
  // durations and the final error are authoritative.
  const streamRun = useCallback(
    (runId: string) => {
      streamRef.current?.();
      pollingRef.current = false;
      streamRef.current = openGraphRunStream(runId, {
        onEvent: (event) => {
          const current = useGraphEditor.getState().run;
          if (!current || current.id !== runId) return;
          const next = { ...current, events: [...(current.events ?? []), event] };
          if (event.nodeId) {
            const status = nodeStatusFromEvent(event.kind);
            if (status) next.nodeStatus = { ...(current.nodeStatus ?? {}), [event.nodeId]: status };
          }
          if (event.kind === 'run.started' || event.kind === 'run.resumed') next.status = 'running';
          setRun(next);
          if (isRunTerminalEvent(event.kind)) void refreshRun(runId);
        },
        onEnd: () => { void refreshRun(runId); },
        onError: () => {
          streamRef.current?.();
          streamRef.current = null;
          setError('Live stream disconnected — falling back to polling.');
          void pollUntilDone(runId);
        },
      });
    },
    [setRun, refreshRun, pollUntilDone],
  );

  useEffect(() => () => {
    streamRef.current?.();
    streamRef.current = null;
    pollingRef.current = false;
  }, []);

  const startRun = useCallback(async () => {
    if (!workflowId) return;
    setRunBusy(true);
    setError(null);
    try {
      const record = await startWorkflowRun(workflowId);
      setRun(record);
      setRightTab('run');
      streamRun(record.id);
    } catch (err) {
      if (err instanceof GraphRunApiError) setError(err.message);
      else setError(err instanceof Error ? err.message : 'Failed to start the run');
      setRightTab('run');
    } finally {
      setRunBusy(false);
    }
  }, [workflowId, setRun, streamRun]);

  const stopRun = useCallback(async () => {
    if (!run) return;
    const close = streamRef.current;
    streamRef.current = null;
    close?.();
    pollingRef.current = false;
    try {
      setRun(await cancelGraphRun(run.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel the run');
    }
  }, [run, setRun]);

  const runBlockReason = useMemo(() => {
    if (!workflowId) return 'Save this workflow before running it — the runtime executes the persisted version.';
    if (dirty) return 'Save your changes first — the runtime executes the persisted version.';
    if (errorCount > 0) return 'Fix the validation errors before running.';
    return null;
  }, [workflowId, dirty, errorCount]);
  const canRun = runBlockReason === null && !runBusy;

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Canvas column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
          <GitBranch size={15} className="shrink-0 text-sky-400" />
          <input
            value={ir?.name ?? ''}
            disabled={!ir}
            placeholder={ir ? 'Workflow name' : 'Graph Studio'}
            onChange={(e) => dispatch({ op: 'set_meta', name: e.target.value })}
            className="min-w-0 flex-1 rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[13px] font-medium outline-none focus:border-sky-400/50 disabled:opacity-50"
          />
          {ir && (
            <span className="shrink-0 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-muted-foreground">
              v{baseVersion}
            </span>
          )}
          <span className={cn('shrink-0 text-[10px]', dirty ? 'text-amber-400' : 'text-emerald-400')}>
            {ir ? (dirty ? 'Unsaved changes' : 'Saved') : ''}
          </span>
          {notice && <span className="shrink-0 text-[10px] text-sky-300">{notice}</span>}

          <select
            value={ir?.settings.executionMode ?? 'research'}
            disabled={!ir}
            onChange={(e) => dispatch({ op: 'set_settings', settings: { executionMode: e.target.value as ExecutionMode } })}
            className="shrink-0 rounded-md border border-white/10 bg-background/60 px-1.5 py-1 text-[11px] outline-none disabled:opacity-50"
            title="Execution mode"
          >
            {MODES.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>

          <div className="ml-1 flex shrink-0 items-center gap-1">
            <button type="button" disabled={!ir || past === 0} onClick={undo} title="Undo (Ctrl+Z)" className="rounded-md border border-white/10 p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30">
              <Undo2 size={13} />
            </button>
            <button type="button" disabled={!ir || future === 0} onClick={redo} title="Redo (Ctrl+Shift+Z)" className="rounded-md border border-white/10 p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30">
              <Redo2 size={13} />
            </button>
            <button type="button" disabled={!ir} onClick={applyAutoLayout} title="Auto-layout" className="rounded-md border border-white/10 p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30">
              <LayoutGrid size={13} />
            </button>
            <button type="button" disabled={!ir} onClick={() => fitRef.current?.()} title="Fit view" className="rounded-md border border-white/10 p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30">
              <ScanSearch size={13} />
            </button>
            <button
              type="button"
              disabled={!ir || busy || errorCount > 0}
              onClick={() => void save()}
              title={errorCount > 0 ? 'Fix validation errors before saving' : 'Save (Ctrl+S)'}
              className="flex items-center gap-1.5 rounded-md border border-sky-400/30 bg-sky-500/10 px-2.5 py-1.5 text-[11px] text-sky-200 hover:bg-sky-500/20 disabled:opacity-40"
            >
              {dirty ? <Save size={13} /> : <Check size={13} />} Save
            </button>
            <button
              type="button"
              disabled={!canRun}
              onClick={() => void startRun()}
              title={runBlockReason ?? 'Run a test execution of the saved version'}
              className="flex items-center gap-1.5 rounded-md border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1.5 text-[11px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-40"
            >
              <Play size={12} /> Test run
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 border-b border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-[11px] text-rose-200">
            <span className="flex-1">{error}</span>
            <button type="button" onClick={() => setError(null)}><X size={12} /></button>
          </div>
        )}

        <div className="relative min-h-0 flex-1">
          {ir ? (
            <GraphCanvas onSave={save} fitViewRef={fitRef} />
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="glass-card max-w-sm rounded-2xl border border-white/10 p-6 text-center">
                <GitBranch size={28} className="mx-auto mb-3 text-sky-400" />
                <h2 className="text-[15px] font-medium text-foreground">Graph Studio</h2>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  Create a workflow or open one from the panel on the left to start building.
                </p>
                <button
                  type="button"
                  onClick={() => setTemplatesOpen(true)}
                  className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-sky-400/30 bg-sky-500/10 px-3 py-1.5 text-[12px] text-sky-200 hover:bg-sky-500/20"
                >
                  <Plus size={13} /> New workflow
                </button>
                {templatesOpen && (
                  <div className="mt-3 space-y-1 text-left">
                    {WORKFLOW_TEMPLATES.map((template) => (
                      <button
                        key={template.id}
                        type="button"
                        onClick={() => {
                          setTemplatesOpen(false);
                          void createFromTemplate(template.id);
                        }}
                        className="block w-full rounded-md border border-white/10 px-2 py-1.5 text-left hover:bg-white/5"
                      >
                        <span className="block text-[12px] text-foreground">{template.name}</span>
                        <span className="block text-[10px] text-muted-foreground">{template.description}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right rail: inspector / validation / run console */}
      <aside className="hidden w-[320px] shrink-0 flex-col border-l border-white/10 bg-background/40 xl:flex">
        <div className="flex shrink-0 gap-1 border-b border-white/10 p-2">
          {([
            ['inspect', 'Inspect', null],
            ['issues', `Issues${errorCount > 0 ? ` (${errorCount})` : ''}`, null],
            ['run', 'Run', run?.status ?? null],
            ['history', 'History', null],
          ] as [RightTab, string, string | null][]).map(([tab, label, hint]) => (
            <button
              key={tab}
              type="button"
              onClick={() => setRightTab(tab)}
              className={cn(
                'flex-1 rounded-md px-2 py-1 text-[11px]',
                rightTab === tab ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <span className="flex items-center justify-center gap-1">
                {label}
                {hint && (
                  <span
                    className={cn(
                      'h-1.5 w-1.5 rounded-full',
                      hint === 'running'
                        ? 'bg-sky-400 animate-pulse'
                        : hint === 'succeeded'
                          ? 'bg-emerald-400'
                          : hint === 'failed'
                            ? 'bg-rose-400'
                            : 'bg-slate-500',
                    )}
                  />
                )}
              </span>
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1">
          {rightTab === 'inspect' && <NodeInspector />}
          {rightTab === 'issues' && <ValidationPanel />}
          {rightTab === 'run' && (
            <div className="flex h-full flex-col">
              <div className="min-h-0 flex-1">
                <RunPanel
                  onStart={() => void startRun()}
                  onCancel={() => void stopRun()}
                  busy={runBusy}
                  canRun={canRun}
                  blockReason={runBlockReason}
                />
              </div>
              <ScheduleList workflowId={workflowId && !dirty ? workflowId : null} />
            </div>
          )}
          {rightTab === 'history' && (
            <HistoryPanel
              workflowId={workflowId}
              currentVersion={currentVersion}
              onOpenRun={(record) => {
                setRun(record);
                setRightTab('run');
              }}
              onOpenVersion={(record) => {
                load(record.ir, {
                  workflowId: record.id,
                  baseVersion: record.version,
                  contentHash: record.contentHash,
                });
                setRightTab('inspect');
              }}
            />
          )}
        </div>
      </aside>
    </div>
  );
}
