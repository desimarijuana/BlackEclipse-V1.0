'use client';

// ── Graph Studio — workspace ─────────────────────────────────────────────────
// Two internal views, no router:
//   • home   — the workflow gallery (n8n's "Workflows" landing page)
//   • editor — a full-bleed canvas with a slim header, a node inspector dock and
//              a collapsible execution dock.
// The left app sidebar stays as the quick workflow switcher; the node library now
// lives on the canvas (Tab / "+"), where it belongs.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Check, ChevronLeft, GitBranch, Home, MoreHorizontal, Play, Redo2, Save, Undo2, WarningCircle, X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { useWorkflowCatalog } from '@/lib/graph-studio/catalog-store';
import { createWorkflow, saveWorkflow, WorkflowApiError } from '@/lib/graph-studio/persistence-client';
import {
  cancelGraphRun, getGraphRun, isTerminal, isRunTerminalEvent, nodeStatusFromEvent,
  openGraphRunStream, startWorkflowRun, GraphRunApiError,
} from '@/lib/graph-studio/execution-client';
import type { ExecutionMode } from '@/lib/graph-studio/types';
import { summarizeRunNeeds } from '@/lib/graph-studio/run-authorization';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { GraphCanvas } from './graph-canvas';
import { NodeInspector } from './node-inspector';
import { ValidationPanel } from './validation-panel';
import { ExecutionDock } from './execution-dock';
import { HistoryPanel } from './history-panel';
import { GraphHealthPanel } from './graph-health-panel';
import { GraphHome } from './graph-home';
import { RunAuthorizationDialog } from './run-authorization-dialog';

type WorkspaceView = 'home' | 'editor';
type RightPanel = 'node' | 'issues' | 'history' | 'health' | null;
const MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

export function GraphStudioScreen({ onExit }: { onExit?: () => void }) {
  const ir = useGraphEditor((s) => s.ir);
  const workflowId = useGraphEditor((s) => s.workflowId);
  const baseVersion = useGraphEditor((s) => s.baseVersion);
  const dirty = useGraphEditor((s) => s.dirty);
  const diagnostics = useGraphEditor((s) => s.diagnostics);
  const selection = useGraphEditor((s) => s.selection);
  const load = useGraphEditor((s) => s.load);
  const dispatch = useGraphEditor((s) => s.dispatch);
  const undo = useGraphEditor((s) => s.undo);
  const redo = useGraphEditor((s) => s.redo);
  const applyAutoLayout = useGraphEditor((s) => s.applyAutoLayout);
  const markSaved = useGraphEditor((s) => s.markSaved);
  const setRun = useGraphEditor((s) => s.setRun);
  const run = useGraphEditor((s) => s.run);
  const loadNonce = useGraphEditor((s) => s.loadNonce);
  const past = useGraphEditor((s) => s.past.length);
  const future = useGraphEditor((s) => s.future.length);

  const refreshCatalog = useWorkflowCatalog((s) => s.refresh);
  const summaries = useWorkflowCatalog((s) => s.summaries);
  const currentVersion = useMemo(
    () => summaries.find((summary) => summary.id === workflowId)?.currentVersion ?? baseVersion,
    [summaries, workflowId, baseVersion],
  );

  const streamRef = useRef<(() => void) | null>(null);
  const pollingRef = useRef(false);

  const [view, setView] = useState<WorkspaceView>('home');
  const [rightPanel, setRightPanel] = useState<RightPanel>(null);
  const [busy, setBusy] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [authorizeOpen, setAuthorizeOpen] = useState(false);

  const errorCount = useMemo(() => diagnostics.filter((d) => d.severity === 'error').length, [diagnostics]);
  const runNeeds = useMemo(() => (ir ? summarizeRunNeeds(ir) : null), [ir]);

  useEffect(() => {
    void refreshCatalog();
  }, [refreshCatalog]);

  // Opening a workflow (home card, sidebar browser, template, generated plan)
  // increments `loadNonce`; that is the ONE signal that switches to the editor.
  useEffect(() => {
    if (loadNonce > 0) setView('editor');
  }, [loadNonce]);

  // A selected node opens the inspector; clearing the selection closes it unless
  // another panel (issues/history/health) is pinned open.
  useEffect(() => {
    if (rightPanel === 'issues' || rightPanel === 'history' || rightPanel === 'health') return;
    if (selection.nodeIds.length === 1) setRightPanel('node');
    else if (selection.nodeIds.length === 0) setRightPanel(null);
  }, [selection.nodeIds.length, rightPanel]);

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

  const startRun = useCallback(async (options?: {
    operator?: boolean;
    allowNetwork?: boolean;
    allowPaperTrading?: boolean;
    allowLocalWrite?: boolean;
  }) => {
    if (!workflowId) return;
    setRunBusy(true);
    setError(null);
    try {
      const record = await startWorkflowRun(workflowId, undefined, options);
      setRun(record);
      streamRun(record.id);
    } catch (err) {
      if (err instanceof GraphRunApiError) setError(err.message);
      else setError(err instanceof Error ? err.message : 'Failed to start the run');
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

  const operatorReady = useMemo(() => {
    if (!runNeeds || !ir) return false;
    const mode = ir.settings.executionMode;
    const tradingReady = runNeeds.tradingNodes.length === 0 || mode === 'paper';
    const unsupported = runNeeds.writeNodeTypes.filter((type) => type !== 'video.render');
    return runNeeds.requiresNetwork || runNeeds.tradingNodes.length > 0 || runNeeds.writeNodes.length > 0
      ? canRun && unsupported.length === 0 && tradingReady
      : false;
  }, [runNeeds, ir, canRun]);

  const operatorBlockReason = useMemo(() => {
    if (!runNeeds || !ir) return null;
    const mode = ir.settings.executionMode;
    const unsupported = runNeeds.writeNodeTypes.filter((type) => type !== 'video.render');
    if (unsupported.length > 0) return `External write nodes are not enabled yet: ${runNeeds.writeNodes.join(', ')}`;
    if (runNeeds.tradingNodes.length > 0 && mode === 'live') return 'Live trading is not available; set the workflow mode to paper.';
    if (runNeeds.tradingNodes.length > 0 && mode !== 'paper') return `Paper-trading nodes require paper mode: ${runNeeds.tradingNodes.join(', ')}`;
    return runBlockReason;
  }, [runNeeds, ir, runBlockReason]);

  const backHome = () => {
    if (dirty && !window.confirm('You have unsaved changes. Leave the editor and keep them unsaved?')) return;
    setView('home');
    setRightPanel(null);
    void refreshCatalog();
  };

  if (view === 'home' || !ir) {
    return <GraphHome onOpen={() => setView('editor')} onExit={onExit} />;
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      {/* Slim editor header — name, state, and only the primary actions. */}
      <header className="flex h-11 shrink-0 items-center gap-1.5 border-b border-white/10 px-2.5">
        {onExit && (
          <>
            <Button type="button" variant="ghost" size="icon-sm" onClick={onExit} title="Back to Overview">
              <Home size={14} />
            </Button>
            <span className="h-4 w-px bg-white/10" />
          </>
        )}
        <Button type="button" variant="ghost" size="sm" onClick={backHome} title="Back to workflows">
          <ChevronLeft size={14} /> Workflows
        </Button>
        <span className="mx-0.5 h-4 w-px bg-white/10" />
        <GitBranch size={14} className="shrink-0 text-sky-400" />
        <input
          value={ir.name}
          onChange={(event) => dispatch({ op: 'set_meta', name: event.target.value })}
          placeholder="Workflow name"
          className="min-w-0 max-w-[320px] flex-1 rounded-md border border-transparent bg-transparent px-1 py-0.5 text-[13px] font-semibold text-foreground outline-none hover:border-white/10 focus:border-sky-400/50"
        />
        <span className="shrink-0 rounded-full border border-white/10 px-1.5 py-0.5 text-[9.5px] text-muted-foreground">
          v{currentVersion}
        </span>
        <span className={cn('shrink-0 text-[10px]', dirty ? 'text-amber-400' : 'text-emerald-400')}>
          {dirty ? 'Unsaved' : 'Saved'}
        </span>
        {notice && <span className="shrink-0 text-[10px] text-sky-300">{notice}</span>}

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <select
            value={ir.settings.executionMode}
            onChange={(event) => dispatch({ op: 'set_settings', settings: { executionMode: event.target.value as ExecutionMode } })}
            className="rounded-md border border-white/10 bg-background/60 px-1.5 py-1 text-[10.5px] text-muted-foreground outline-none focus:border-sky-400/50"
            title="Execution mode"
          >
            {MODES.map((mode) => (
              <option key={mode} value={mode}>{mode}</option>
            ))}
          </select>
          <Button type="button" variant="ghost" size="icon-sm" disabled={past === 0} onClick={undo} title="Undo (Ctrl+Z)">
            <Undo2 size={13} />
          </Button>
          <Button type="button" variant="ghost" size="icon-sm" disabled={future === 0} onClick={redo} title="Redo (Ctrl+Shift+Z)">
            <Redo2 size={13} />
          </Button>
          <Button
            type="button"
            variant={rightPanel === 'issues' ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setRightPanel((panel) => (panel === 'issues' ? (selection.nodeIds.length === 1 ? 'node' : null) : 'issues'))}
            title="Validation issues"
            className={cn(errorCount > 0 && 'text-rose-300 hover:text-rose-200')}
          >
            <WarningCircle size={12} />
            {errorCount > 0 ? errorCount : 'Issues'}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!ir || busy || errorCount > 0}
            onClick={() => void save()}
            title={errorCount > 0 ? 'Fix validation errors before saving' : 'Save (Ctrl+S)'}
          >
            {dirty ? <Save size={12} /> : <Check size={12} />} Save
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!canRun}
            onClick={() => void startRun()}
            title={runBlockReason ?? 'Run a test execution of the saved version'}
          >
            <Play size={11} /> Test
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button type="button" variant="ghost" size="icon-sm" title="More actions" />
              }
            >
              <MoreHorizontal size={15} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onClick={() => setRightPanel('history')}>History</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setRightPanel('health')}>Health</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={applyAutoLayout}>Tidy up layout</DropdownMenuItem>
              <DropdownMenuItem
                disabled={!operatorReady}
                onClick={() => setAuthorizeOpen(true)}
                title={operatorBlockReason ?? 'Run with explicit effects'}
              >
                Operator run…
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {error && (
        <div className="flex shrink-0 items-center gap-2 border-b border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-[11px] text-rose-200">
          <span className="flex-1">{error}</span>
          <button type="button" onClick={() => setError(null)}><X size={12} /></button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="relative min-h-0 flex-1">
            <GraphCanvas onSave={save} />
          </div>
          <ExecutionDock
            onStart={() => void startRun()}
            onCancel={() => void stopRun()}
            busy={runBusy}
            canRun={canRun}
            blockReason={runBlockReason}
            workflowId={workflowId && !dirty ? workflowId : null}
          />
        </div>

        {rightPanel && (
          <aside className="flex w-[380px] max-w-[85vw] shrink-0 flex-col border-l border-white/10 bg-background/40">
            {rightPanel === 'node' && <NodeInspector onClose={() => setRightPanel(null)} />}
            {rightPanel === 'issues' && (
              <div className="flex h-full flex-col">
                <div className="flex h-9 shrink-0 items-center justify-between border-b border-white/10 px-3">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Issues</span>
                  <button type="button" onClick={() => setRightPanel(selection.nodeIds.length === 1 ? 'node' : null)} className="rounded p-1 text-muted-foreground hover:text-foreground">
                    <X size={12} />
                  </button>
                </div>
                <div className="min-h-0 flex-1"><ValidationPanel /></div>
              </div>
            )}
            {rightPanel === 'history' && (
              <div className="flex h-full flex-col">
                <div className="flex h-9 shrink-0 items-center justify-between border-b border-white/10 px-3">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">History</span>
                  <button type="button" onClick={() => setRightPanel(null)} className="rounded p-1 text-muted-foreground hover:text-foreground"><X size={12} /></button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <HistoryPanel
                    workflowId={workflowId}
                    currentVersion={currentVersion}
                    onOpenRun={(record) => {
                      setRun(record);
                      setRightPanel(null);
                    }}
                    onOpenVersion={(record) => {
                      load(record.ir, {
                        workflowId: record.id,
                        baseVersion: record.version,
                        contentHash: record.contentHash,
                      });
                      setRightPanel(null);
                    }}
                  />
                </div>
              </div>
            )}
            {rightPanel === 'health' && (
              <div className="flex h-full flex-col">
                <div className="flex h-9 shrink-0 items-center justify-between border-b border-white/10 px-3">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Health</span>
                  <button type="button" onClick={() => setRightPanel(null)} className="rounded p-1 text-muted-foreground hover:text-foreground"><X size={12} /></button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto"><GraphHealthPanel /></div>
              </div>
            )}
          </aside>
        )}
      </div>

      {authorizeOpen && runNeeds && (
        <RunAuthorizationDialog
          needs={runNeeds}
          onCancel={() => setAuthorizeOpen(false)}
          onConfirm={() => {
            setAuthorizeOpen(false);
            void startRun({
              operator: true,
              allowNetwork: runNeeds.requiresNetwork,
              allowPaperTrading: runNeeds.tradingNodes.length > 0,
              allowLocalWrite: runNeeds.writeNodes.length > 0,
            });
          }}
        />
      )}
    </div>
  );
}
