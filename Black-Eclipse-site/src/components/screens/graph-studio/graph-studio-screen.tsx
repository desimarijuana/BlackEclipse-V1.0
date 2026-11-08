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
  Check, ChevronDown, ChevronLeft, GitBranch, MoreHorizontal, Play, Redo2, Save, Sparkles, Undo2, WarningCircle, X,
  Activity, History, Settings2,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useGraphEditor } from '@/lib/graph-studio/editor-store';
import { useWorkflowCatalog } from '@/lib/graph-studio/catalog-store';
import { createWorkflow, saveWorkflow, WorkflowApiError } from '@/lib/graph-studio/persistence-client';
import { AUTO_SAVE_DELAY_MS, shouldAutoSave } from '@/lib/graph-studio/autosave';
import { contentHash } from '@/lib/graph-studio/hash';
import {
  cancelGraphRun, getGraphRun, isTerminal, isRunTerminalEvent, nodeStatusFromEvent,
  openGraphRunStream, startWorkflowRun, GraphRunApiError,
} from '@/lib/graph-studio/execution-client';
import type { ExecutionMode } from '@/lib/graph-studio/types';
import { summarizeRunNeeds } from '@/lib/graph-studio/run-authorization';
import { parseRunInputText } from '@/lib/graph-studio/run-input';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { listAutomations, type AutomationView } from '@/lib/harness/automation-browser';
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
import { AssistantPanel } from './assistant-panel';

type WorkspaceView = 'home' | 'editor';
type RightPanel = 'node' | 'issues' | 'history' | 'health' | 'assistant' | null;
const MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

const RAIL_STORAGE_KEY = 'be_graph_rail_v1';
const RAIL_MIN_WIDTH = 340;
const RAIL_MAX_WIDTH = 760;
const RAIL_DEFAULT_WIDTH = 420;
const RAIL_TABS: Array<{ id: Exclude<RightPanel, null>; label: string; icon: typeof Sparkles }> = [
  { id: 'assistant', label: 'Assistant', icon: Sparkles },
  { id: 'node', label: 'Node', icon: Settings2 },
  { id: 'issues', label: 'Issues', icon: WarningCircle },
  { id: 'history', label: 'History', icon: History },
  { id: 'health', label: 'Health', icon: Activity },
];

function readRailState(): { tab: Exclude<RightPanel, null>; width: number } {
  if (typeof window === 'undefined') return { tab: 'assistant', width: RAIL_DEFAULT_WIDTH };
  try {
    const raw = window.localStorage.getItem(RAIL_STORAGE_KEY);
    if (!raw) return { tab: 'assistant', width: RAIL_DEFAULT_WIDTH };
    const parsed = JSON.parse(raw) as { tab?: unknown; width?: unknown };
    const tab = RAIL_TABS.some((item) => item.id === parsed.tab)
      ? (parsed.tab as Exclude<RightPanel, null>)
      : 'assistant';
    const width = typeof parsed.width === 'number' && Number.isFinite(parsed.width)
      ? Math.max(RAIL_MIN_WIDTH, Math.min(RAIL_MAX_WIDTH, Math.round(parsed.width)))
      : RAIL_DEFAULT_WIDTH;
    return { tab, width };
  } catch {
    return { tab: 'assistant', width: RAIL_DEFAULT_WIDTH };
  }
}

export function GraphStudioScreen({
  eyebrow = 'Graph Studio',
  title = 'Workflows',
  subtitle = 'Build, validate and run typed workflows. Every graph compiles to the same workflow model.',
  onViewChange,
}: {
  eyebrow?: string;
  title?: string;
  subtitle?: string;
  /** Reports whether the workspace is showing the editor (shell hides its top bar). */
  onViewChange?: (editing: boolean) => void;
}) {
  const ir = useGraphEditor((s) => s.ir);
  const workflowId = useGraphEditor((s) => s.workflowId);
  const baseVersion = useGraphEditor((s) => s.baseVersion);
  const serverContentHash = useGraphEditor((s) => s.serverContentHash);
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
  // The editor's right rail is a real sidebar: a vertical tab strip plus a
  // resizable panel. The active tab and width survive reloads.
  const [rightPanel, setRightPanel] = useState<RightPanel>(() => {
    if (typeof window === 'undefined') return null;
    try {
      const raw = window.localStorage.getItem(RAIL_STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as { open?: unknown };
      return parsed.open === true ? readRailState().tab : null;
    } catch {
      return null;
    }
  });
  const [railWidth, setRailWidth] = useState(() => readRailState().width);
  const lastPanelRef = useRef<Exclude<RightPanel, null>>(readRailState().tab);
  // The node whose inspector the user actually asked for with a click. Kept
  // apart from selection so dragging a node (which selects it on pointer-down)
  // never pops the inspector open.
  const [inspectedNodeId, setInspectedNodeId] = useState<string | null>(null);
  const openRail = useCallback((tab: Exclude<RightPanel, null>) => {
    lastPanelRef.current = tab;
    setRightPanel(tab);
  }, []);
  const toggleRail = useCallback((tab: Exclude<RightPanel, null>) => {
    setRightPanel((current) => (current === tab ? null : tab));
  }, []);

  useEffect(() => {
    if (rightPanel) lastPanelRef.current = rightPanel;
    try {
      window.localStorage.setItem(
        RAIL_STORAGE_KEY,
        JSON.stringify({ open: rightPanel !== null, tab: rightPanel ?? lastPanelRef.current, width: railWidth }),
      );
    } catch {
      /* storage may be unavailable; the rail still works for this session */
    }
  }, [rightPanel, railWidth]);

  const startRailResize = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = railWidth;
    const move = (pointer: PointerEvent) => {
      setRailWidth(Math.max(RAIL_MIN_WIDTH, Math.min(RAIL_MAX_WIDTH, startWidth + (startX - pointer.clientX))));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }, [railWidth]);

  const [busy, setBusy] = useState(false);
  // Auto-save is ON by default (persisted per browser). Invalid graphs are
  // never auto-saved, exactly like the Save button.
  const [autoSave, setAutoSave] = useState(() => {
    if (typeof window === 'undefined') return true;
    try {
      return window.localStorage.getItem('be_graph_autosave_v1') !== 'off';
    } catch {
      return true;
    }
  });
  const autoSavingRef = useRef(false);
  const [runBusy, setRunBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [authorizeOpen, setAuthorizeOpen] = useState(false);
  // A workflow can be the brain of a bot; show that bot's face in the header.
  useHydrateBotAvatars();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const [linkedBot, setLinkedBot] = useState<AutomationView | null>(null);
  useEffect(() => {
    if (!workflowId) {
      setLinkedBot(null);
      return;
    }
    let live = true;
    void listAutomations()
      .then((items) => {
        if (!live) return;
        setLinkedBot(
          items.find(
            (item) => item.action.type === 'execute_workflow' && item.action.workflowId === workflowId,
          ) ?? null,
        );
      })
      .catch(() => { if (live) setLinkedBot(null); });
    return () => { live = false; };
  }, [workflowId]);
  // One-off trigger input for the next run. Text lives in the execution dock;
  // it is parsed here so both the dock button and the operator dialog use it.
  const [runInputText, setRunInputText] = useState('');
  const runInput = useMemo(() => parseRunInputText(runInputText), [runInputText]);
  const runInputError = runInput.ok ? null : runInput.error;

  // A one-off input belongs to one workflow; never carry it across a switch.
  useEffect(() => {
    setRunInputText('');
  }, [workflowId]);

  const errorCount = useMemo(() => diagnostics.filter((d) => d.severity === 'error').length, [diagnostics]);
  const runNeeds = useMemo(() => (ir ? summarizeRunNeeds(ir) : null), [ir]);
  const needsOperatorRun = useMemo(
    () => Boolean(
      runNeeds
      && (runNeeds.requiresNetwork
        || runNeeds.tradingNodes.length > 0
        || runNeeds.writeNodes.length > 0),
    ),
    [runNeeds],
  );

  useEffect(() => {
    void refreshCatalog();
  }, [refreshCatalog]);

  // Opening a workflow (home card, sidebar browser, template, generated plan)
  // increments `loadNonce`; that is the ONE signal that switches to the editor.
  useEffect(() => {
    if (loadNonce > 0) setView('editor');
  }, [loadNonce]);

  // Tell the shell whether this workspace is in the gallery or the editor, so
  // the app header can stay visible on Overview and disappear in the editor.
  const editing = view === 'editor' && Boolean(ir);
  useEffect(() => {
    onViewChange?.(editing);
  }, [editing, onViewChange]);

  // A CLICKED node opens the inspector. Selection alone (a drag, or a marquee)
  // does not: the rail follows `inspectedNodeId`, and switches back off the
  // inspector when that node leaves a single-node selection. The user's explicit
  // tab choice is preserved; a selection change never closes the rail.
  const singleSelectedId = selection.nodeIds.length === 1 ? selection.nodeIds[0] : null;
  useEffect(() => {
    // Only a selection/inspection change moves the rail. The user's explicit
    // tab choice must win, so `rightPanel` is deliberately not a dependency.
    if (singleSelectedId && singleSelectedId === inspectedNodeId) {
      setRightPanel((current) => (current === 'node' ? current : 'node'));
    } else {
      setRightPanel((current) => (current === 'node' ? null : current));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [singleSelectedId, inspectedNodeId]);

  const save = useCallback(async (): Promise<boolean> => {
    const current = useGraphEditor.getState().ir;
    if (!current) return false;
    setBusy(true);
    setError(null);
    let ok = false;
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
      ok = true;
      setTimeout(() => setNotice(null), 2500);
    } catch (err) {
      if (err instanceof WorkflowApiError) setError(err.message);
      else setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setBusy(false);
    }
    return ok;
  }, [workflowId, load, markSaved, refreshCatalog]);

  // Auto-save: a short pause after the last edit persists the graph, so an
  // operator never loses work by closing the tab. The policy is a pure function
  // (`shouldAutoSave`) so it matches the Save button exactly.
  useEffect(() => {
    const currentHash = ir ? contentHash(ir) : null;
    const allowed = shouldAutoSave({
      enabled: autoSave,
      dirty,
      busy,
      errors: errorCount,
      hasWorkflow: Boolean(workflowId),
      hasIr: Boolean(ir),
      changed: Boolean(currentHash) && currentHash !== serverContentHash,
    });
    if (!allowed || autoSavingRef.current) return;
    const timer = setTimeout(() => {
      if (autoSavingRef.current) return;
      autoSavingRef.current = true;
      void save().finally(() => { autoSavingRef.current = false; });
    }, AUTO_SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [autoSave, workflowId, ir, dirty, busy, errorCount, save, serverContentHash]);

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
    allowWriteScopes?: string[];
    allowLiveTrading?: boolean;
  }) => {
    if (!workflowId) return;
    if (!runInput.ok) {
      setError(runInput.error);
      return;
    }
    setRunBusy(true);
    setError(null);
    try {
      const record = await startWorkflowRun(workflowId, undefined, {
        ...options,
        ...(runInput.value !== undefined ? { runInput: runInput.value } : {}),
      });
      setRun(record);
      streamRun(record.id);
    } catch (err) {
      if (err instanceof GraphRunApiError) setError(err.message);
      else setError(err instanceof Error ? err.message : 'Failed to start the run');
    } finally {
      setRunBusy(false);
    }
  }, [workflowId, setRun, streamRun, runInput]);

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
  const canRun = runBlockReason === null && !runBusy && runInputError === null;

  const operatorReady = useMemo(() => {
    if (!runNeeds || !ir) return false;
    const mode = ir.settings.executionMode;
    const tradingReady =
      runNeeds.tradingNodes.length === 0 || mode === 'paper' || mode === 'live';
    const unsupported = runNeeds.writeNodeTypes.filter(
      (type) => type !== 'video.render' && type !== 'file.write',
    );
    return runNeeds.requiresNetwork || runNeeds.tradingNodes.length > 0 || runNeeds.writeNodes.length > 0
      ? canRun && unsupported.length === 0 && tradingReady
      : false;
  }, [runNeeds, ir, canRun]);

  // A block that holds regardless of the dirty flag (unsupported effects or a
  // mode mismatch). Kept separate from `runBlockReason` so the Start handler can
  // re-check it AFTER a save without reading a stale "unsaved" render value.
  const operatorHardBlock = useMemo(() => {
    if (!runNeeds || !ir) return null;
    const mode = ir.settings.executionMode;
    const unsupported = runNeeds.writeNodeTypes.filter(
      (type) => type !== 'video.render' && type !== 'file.write',
    );
    if (unsupported.length > 0) return `External write nodes are not enabled yet: ${runNeeds.writeNodes.join(', ')}`;
    if (runNeeds.tradingNodes.length > 0 && mode !== 'paper' && mode !== 'live') {
      return `Trading nodes require paper or live mode: ${runNeeds.tradingNodes.join(', ')}`;
    }
    return null;
  }, [runNeeds, ir]);

  const operatorBlockReason = useMemo(
    () => operatorHardBlock ?? runBlockReason,
    [operatorHardBlock, runBlockReason],
  );

  const backHome = () => {
    if (dirty && !window.confirm('You have unsaved changes. Leave the editor and keep them unsaved?')) return;
    setView('home');
    setRightPanel(null);
    void refreshCatalog();
  };

  if (view === 'home' || !ir) {
    return <GraphHome onOpen={() => setView('editor')} eyebrow={eyebrow} title={title} subtitle={subtitle} />;
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      {/* Editor header — identity on the left, run/save actions on the right. */}
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-white/10 bg-background/30 px-3">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={backHome}
          title="Back to Overview"
          className="gap-1.5 text-muted-foreground"
        >
          <ChevronLeft size={14} /> <span className="hidden sm:inline">Overview</span>
        </Button>
        <span className="h-4 w-px bg-white/10" />

        {linkedBot ? (
          <span
            title={`Bot: ${linkedBot.name}`}
            className="relative flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-lg ring-1 ring-inset ring-primary/20"
          >
            <BotAvatar
              botId={linkedBot.id}
              spec={avatarFor(avatars, linkedBot.id)}
              size={28}
              title={linkedBot.name}
            />
            {dirty && (
              <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-amber-400 ring-1 ring-background" />
            )}
          </span>
        ) : (
          <span className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary ring-1 ring-inset ring-primary/20">
            <GitBranch size={14} />
            {dirty && (
              <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-amber-400 ring-1 ring-background" />
            )}
          </span>
        )}

        <div className="flex min-w-0 items-center gap-2">
          <input
            value={ir.name}
            onChange={(event) => dispatch({ op: 'set_meta', name: event.target.value })}
            placeholder="Workflow name"
            size={Math.min(Math.max(ir.name.length || 1, 10), 34)}
            title="Rename workflow"
            className="min-w-[10ch] max-w-[260px] rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-[13px] font-semibold tracking-tight text-foreground outline-none hover:border-white/10 focus:border-primary/50"
          />
          <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.03] px-1.5 py-0.5 text-[9.5px] font-medium tabular-nums text-muted-foreground">
            v{currentVersion}
          </span>
          <span
            className={cn(
              'flex shrink-0 items-center gap-1 text-[10px] font-medium',
              dirty ? 'text-amber-400' : 'text-emerald-400/90',
            )}
            title={dirty
              ? (autoSave ? 'Unsaved — auto-save will persist shortly' : 'Unsaved changes')
              : 'All changes saved'}
          >
            <span className={cn('h-1.5 w-1.5 rounded-full', dirty ? 'bg-amber-400' : 'bg-emerald-400')} />
            {busy ? 'Saving…' : dirty ? 'Unsaved' : 'Saved'}
          </span>
          {notice && <span className="shrink-0 truncate text-[10px] text-primary">{notice}</span>}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  title="Execution mode"
                  className="flex cursor-pointer items-center gap-1.5 rounded-md border border-white/10 bg-background/60 px-2 py-1 text-[10.5px] font-medium text-foreground outline-none transition-colors hover:border-white/20 focus-visible:border-sky-400/50"
                />
              }
            >
              <span className="hidden text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/60 lg:inline">
                Mode
              </span>
              <span className="capitalize">{ir.settings.executionMode}</span>
              <ChevronDown size={11} className="text-muted-foreground" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-36">
              {MODES.map((mode) => (
                <DropdownMenuItem
                  key={mode}
                  onClick={() => dispatch({ op: 'set_settings', settings: { executionMode: mode as ExecutionMode } })}
                >
                  <span className="flex-1 capitalize">{mode}</span>
                  {ir.settings.executionMode === mode && <Check size={12} className="opacity-70" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <span className="mx-0.5 h-4 w-px bg-white/10" />
          <Button type="button" variant="ghost" size="icon-sm" disabled={past === 0} onClick={undo} title="Undo (Ctrl+Z)">
            <Undo2 size={13} />
          </Button>
          <Button type="button" variant="ghost" size="icon-sm" disabled={future === 0} onClick={redo} title="Redo (Ctrl+Shift+Z)">
            <Redo2 size={13} />
          </Button>

          <span className="mx-0.5 h-4 w-px bg-white/10" />
          <Button
            type="button"
            variant={rightPanel === 'assistant' ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => toggleRail('assistant')}
            title="Workflow assistant"
            className="gap-1.5"
          >
            <Sparkles size={12} />
            <span className="hidden sm:inline">Assistant</span>
          </Button>
          <Button
            type="button"
            variant={rightPanel === 'issues' ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setRightPanel((panel) => (panel === 'issues' ? (selection.nodeIds.length === 1 ? 'node' : null) : 'issues'))}
            title="Validation issues"
            className={cn('gap-1.5', errorCount > 0 && 'text-rose-300 hover:text-rose-200')}
          >
            <WarningCircle size={12} />
            <span className={cn(errorCount > 0 && 'tabular-nums')}>{errorCount > 0 ? errorCount : 'Issues'}</span>
          </Button>

          <button
            type="button"
            onClick={() => {
              setAutoSave((current) => {
                const next = !current;
                try {
                  window.localStorage.setItem('be_graph_autosave_v1', next ? 'on' : 'off');
                } catch { /* storage may be unavailable; keep the in-memory choice */ }
                return next;
              });
            }}
            aria-pressed={autoSave}
            title={autoSave
              ? 'Auto-save is on — edits are persisted after a short pause'
              : 'Auto-save is off — use Save (Ctrl+S)'}
            className={cn(
              'flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-[10.5px] font-medium transition-colors',
              autoSave
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/15'
                : 'border-white/10 bg-background/60 text-muted-foreground hover:text-foreground',
            )}
          >
            <span className={cn('h-1.5 w-1.5 rounded-full', autoSave ? 'bg-emerald-400' : 'bg-slate-500')} />
            Auto-save
          </button>

          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!ir || busy || errorCount > 0}
            onClick={() => void save()}
            title={errorCount > 0 ? 'Fix validation errors before saving' : 'Save (Ctrl+S)'}
            className="gap-1.5"
          >
            {dirty ? <Save size={12} /> : <Check size={12} />} Save
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!workflowId || errorCount > 0 || runBusy || runInputError !== null || run?.status === 'running'}
            onClick={() => {
              // A graph with network / trading / write effects cannot be a test
              // run. Offer the authorization path instead of firing a run the
              // runtime is guaranteed to refuse.
              const proceed = () => {
                if (!needsOperatorRun) {
                  void startRun();
                  return;
                }
                if (operatorHardBlock) {
                  setError(operatorHardBlock);
                  return;
                }
                setAuthorizeOpen(true);
              };
              if (dirty) {
                void save().then((ok) => { if (ok) proceed(); });
              } else {
                proceed();
              }
            }}
            title={
              !workflowId
                ? 'Save the workflow once before running it'
                : errorCount > 0
                  ? 'Fix the validation errors before running'
                  : dirty
                    ? 'Save the current changes and run the workflow'
                    : runBlockReason
                      ?? (needsOperatorRun
                        ? 'Run this workflow with the effects it declares'
                        : 'Run a test execution of the saved version')
            }
            className="gap-1.5"
          >
            <Play size={11} />
            {runBusy ? 'Starting…' : run?.status === 'running' ? 'Running…' : dirty ? 'Save & run' : 'Start workflow'}
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
              <DropdownMenuItem onClick={() => applyAutoLayout()}>Tidy up layout</DropdownMenuItem>
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
            <GraphCanvas onSave={save} onInspectNode={setInspectedNodeId} />
          </div>
          <ExecutionDock
            onStart={() => void startRun()}
            onCancel={() => void stopRun()}
            busy={runBusy}
            canRun={canRun}
            blockReason={runBlockReason}
            workflowId={workflowId && !dirty ? workflowId : null}
            runInputText={runInputText}
            onRunInputChange={setRunInputText}
            runInputError={runInputError}
          />
        </div>

        {rightPanel && (
          <div
            onPointerDown={startRailResize}
            title="Drag to resize"
            className="w-1 shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-primary/30"
          />
        )}
        {rightPanel && (
          <aside
            style={{ width: railWidth }}
            className="graph-panel flex max-w-[85vw] shrink-0 border-l border-white/10"
          >
            <div className="flex w-10 shrink-0 flex-col items-center gap-1 border-r border-white/10 py-1.5">
              {RAIL_TABS.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => openRail(tab.id)}
                    title={tab.label}
                    aria-label={tab.label}
                    aria-pressed={rightPanel === tab.id}
                    className={cn(
                      'flex h-8 w-8 items-center justify-center rounded-lg transition-colors',
                      rightPanel === tab.id
                        ? 'bg-primary/15 text-primary'
                        : 'text-muted-foreground hover:bg-white/5 hover:text-foreground',
                    )}
                  >
                    <Icon size={14} />
                  </button>
                );
              })}
              <button
                type="button"
                onClick={() => setRightPanel(null)}
                title="Close sidebar"
                aria-label="Close sidebar"
                className="mt-auto flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
              >
                <X size={13} />
              </button>
            </div>
            <div className="flex min-w-0 flex-1 flex-col">
              {rightPanel === 'node' && (
                <NodeInspector
                  onClose={() => {
                    setRightPanel(null);
                    setInspectedNodeId(null);
                  }}
                />
              )}
              {/* Kept mounted across tab switches so an in-flight turn is not
                  cancelled merely because the operator looked at the inspector. */}
              <div className={cn('flex min-h-0 min-w-0 flex-1 flex-col', rightPanel === 'assistant' ? '' : 'hidden')}>
                <AssistantPanel onClose={() => setRightPanel(null)} />
              </div>
              {rightPanel === 'issues' && (
                <div className="flex h-full flex-col">
                  <div className="flex h-9 shrink-0 items-center justify-between border-b border-white/10 px-3">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Issues</span>
                    <button
                      type="button"
                      onClick={() => {
                        if (selection.nodeIds.length === 1) {
                          setInspectedNodeId(selection.nodeIds[0]);
                          setRightPanel('node');
                        } else {
                          setRightPanel(null);
                        }
                      }}
                      className="rounded p-1 text-muted-foreground hover:text-foreground"
                    >
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
            </div>
          </aside>
        )}
      </div>

      {authorizeOpen && runNeeds && (
        <RunAuthorizationDialog
          needs={{
            ...runNeeds,
            liveTrading:
              runNeeds.tradingNodes.length > 0 && ir?.settings.executionMode === 'live',
          }}
          onCancel={() => setAuthorizeOpen(false)}
          onConfirm={() => {
            setAuthorizeOpen(false);
            void startRun({
              operator: true,
              allowNetwork: runNeeds.requiresNetwork,
              allowPaperTrading: runNeeds.tradingNodes.length > 0,
              allowLocalWrite: runNeeds.writeNodeTypes.includes('video.render'),
              allowWriteScopes: runNeeds.writeScopes,
              allowLiveTrading:
                runNeeds.tradingNodes.length > 0 && ir?.settings.executionMode === 'live',
            });
          }}
        />
      )}
    </div>
  );
}
