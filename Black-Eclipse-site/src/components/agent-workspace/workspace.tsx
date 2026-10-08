'use client';

// ── Agent Workspace — the execution-observability dock ─────────────────────────
// A floating, frosted-glass panel that reflects what the agent is doing. It is
// mounted GLOBALLY (root layout, portaled to <body>) and coexists with the app's
// left navigation rail and every screen — it modifies neither.
//
// It reads the live normalized state from `useWorkspaceStore`, which is fed by
// the existing chat SSE stream. It owns no agent logic and never talks to the
// runtime except to replay a finished run's persisted trace.

import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Pin, PinOff, Sparkles, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/i18n/types';
import { useWorkspaceStore, hydrateWorkspaceStore, ALL_PANELS, type WorkspacePanel } from '@/lib/agent-workspace/store';
import { fetchRunTrace, replayTrace } from '@/lib/agent-workspace/history';
import type { AgentWorkspaceState, ArtifactRef } from '@/lib/agent-workspace/types';
import { OverviewPanel } from './overview-panel';
import { ActivityPanel } from './activity-panel';
import { TasksPanel } from './tasks-panel';
import { ChangesPanel } from './changes-panel';
import { ContextPanel } from './context-panel';
import { TelemetryPanel } from './telemetry-panel';
import { PermissionsPanel } from './permissions-panel';
import { ArtifactsPanel } from './artifacts-panel';
import { ResearchPanel, BrowserPanel, ComputerPanel } from './tool-panels';
import { HistoryPanel } from './history-panel';
import { ArtifactViewer, type LoadedContent } from './viewer';
import { PANEL_ICONS, statusIcon } from './ui';

const PANEL_KEY: Record<WorkspacePanel, TranslationKey> = {
  overview: 'workspace.panel.overview',
  activity: 'workspace.panel.activity',
  tasks: 'workspace.panel.tasks',
  changes: 'workspace.panel.changes',
  context: 'workspace.panel.context',
  terminal: 'workspace.panel.terminal',
  research: 'workspace.panel.research',
  browser: 'workspace.panel.browser',
  computer: 'workspace.panel.computer',
  artifacts: 'workspace.panel.artifacts',
  permissions: 'workspace.panel.permissions',
  telemetry: 'workspace.panel.telemetry',
  history: 'workspace.panel.history',
};

const STATUS_KEY: Record<import('@/lib/agent-workspace/types').AgentStatus, TranslationKey> = {
  idle: 'workspace.status.idle',
  planning: 'workspace.status.planning',
  running: 'workspace.status.running',
  waiting: 'workspace.status.waiting',
  paused: 'workspace.status.paused',
  completed: 'workspace.status.completed',
  failed: 'workspace.status.failed',
  cancelled: 'workspace.status.cancelled',
};

/** Which panels show a live "attention" dot (a running subsystem owns them). */
function panelAttention(panel: WorkspacePanel, state: AgentWorkspaceState): boolean {
  if (panel === 'permissions') return state.permissions.some((p) => p.status === 'pending');
  if (panel === 'research') return Boolean(state.research?.active);
  if (panel === 'browser') return Boolean(state.browser?.active);
  if (panel === 'computer') return Boolean(state.computer?.active);
  if (panel === 'activity') return state.execution.status === 'running' || state.execution.status === 'planning';
  return false;
}

export function AgentWorkspace() {
  const open = useWorkspaceStore((s) => s.open);
  const state = useWorkspaceStore((s) => s.state);
  const activePanel = useWorkspaceStore((s) => s.activePanel);
  const pinned = useWorkspaceStore((s) => s.pinned);
  const runId = useWorkspaceStore((s) => s.runId);
  const setActivePanel = useWorkspaceStore((s) => s.setActivePanel);
  const togglePinned = useWorkspaceStore((s) => s.togglePinned);
  const setOpen = useWorkspaceStore((s) => s.setOpen);
  const t = useT();

  const [mounted, setMounted] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [viewing, setViewing] = useState<ArtifactRef | null>(null);
  const [replayState, setReplayState] = useState<AgentWorkspaceState | null>(null);

  useEffect(() => {
    setMounted(true);
    hydrateWorkspaceStore();
  }, []);

  // Tick once a second ONLY while the run is live, so elapsed time advances
  // without a perpetual re-render loop when idle.
  const live = state.execution.status === 'running' || state.execution.status === 'planning' || state.execution.status === 'waiting';
  useEffect(() => {
    if (!open || !live) return;
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [open, live]);

  const effective = replayState ?? state;

  const onDecide = useMemo(
    () => async (id: string, approve: boolean) => {
      try {
        const res = await fetch(`/api/harness/mcp/approvals/${encodeURIComponent(id)}/decide`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ approve }),
        });
        if (!res.ok) throw new Error('decide failed');
      } catch {
        // The runtime's `approval.resolved` event is authoritative; a failed POST
        // leaves the card in place so the operator can retry.
      }
    },
    [],
  );

  const loadArtifact = useMemo(
    () =>
      async (artifact: ArtifactRef): Promise<LoadedContent | null> => {
        if (!runId) return null;
        try {
          const { toolExecutions } = await fetchRunTrace(runId);
          const key = artifact.storageRef ?? artifact.id;
          const row =
            toolExecutions.find((r) => r.toolCallId && (r.toolCallId === key || artifact.id.includes(r.toolCallId))) ??
            toolExecutions.find((r) => artifact.name.includes(r.name ?? '\u0000'));
          if (row?.text) return { content: row.text, truncated: row.text.length >= 4000 };
          return null;
        } catch {
          return null;
        }
      },
    [runId],
  );

  const openRun = useMemo(
    () =>
      async (id: string) => {
        try {
          const { events } = await fetchRunTrace(id);
          setReplayState(replayTrace(id, events));
        } catch {
          setReplayState(null);
        }
      },
    [],
  );

  if (!mounted || !open) return null;

  const statusKey = STATUS_KEY[effective.execution.status];

  return createPortal(
    <div
      role="complementary"
      aria-label={t('workspace.title')}
      className="glass-card-strong fixed bottom-3 right-3 top-16 z-[80] flex w-[min(420px,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-white/12 shadow-2xl"
    >
      <header className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
        <Sparkles size={14} className="shrink-0 text-primary" />
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold text-foreground">
          {t('workspace.title')}
        </span>
        <span className="flex items-center gap-1 text-[10.5px] text-muted-foreground/70">
          {statusIcon(effective.execution.status, 11)}
          {t(statusKey)}
        </span>
        <button
          type="button"
          onClick={() => togglePinned(activePanel)}
          aria-pressed={pinned.includes(activePanel)}
          title={pinned.includes(activePanel) ? t('workspace.unpin') : t('workspace.pin')}
          className={cn(
            'flex h-6 w-6 shrink-0 items-center justify-center rounded-lg transition-colors',
            pinned.includes(activePanel) ? 'bg-white/10 text-primary' : 'text-muted-foreground hover:bg-white/[0.06] hover:text-foreground',
          )}
        >
          {pinned.includes(activePanel) ? <Pin size={12} /> : <PinOff size={12} />}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label={t('workspace.close')}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-white/[0.06] hover:text-foreground"
        >
          <X size={13} />
        </button>
      </header>

      <nav aria-label={t('workspace.title')} className="flex shrink-0 items-center gap-0.5 overflow-x-auto border-b border-white/10 px-2 py-1.5 scrollbar-hide">
        {ALL_PANELS.map((panel) => {
          const Icon = PANEL_ICONS[panel];
          const attention = panelAttention(panel, effective);
          return (
            <button
              key={panel}
              type="button"
              onClick={() => setActivePanel(panel)}
              aria-pressed={activePanel === panel}
              title={t(PANEL_KEY[panel])}
              className={cn(
                'relative flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] transition-colors',
                activePanel === panel ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-foreground',
              )}
            >
              <Icon size={12} />
              <span className="hidden xl:inline">{t(PANEL_KEY[panel])}</span>
              {attention && <span className="absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full bg-primary" />}
            </button>
          );
        })}
      </nav>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col p-3">
        {!effective.runId && effective.activity.length === 0 && activePanel !== 'history' ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <Sparkles size={20} className="text-muted-foreground/30" />
            <p className="text-[12px] leading-relaxed text-muted-foreground/50">{t('workspace.empty')}</p>
          </div>
        ) : (
          <PanelBody
            panel={activePanel}
            state={effective}
            nowMs={nowMs}
            runId={runId}
            onOpenArtifact={setViewing}
            onOpenDiff={(change) => setViewing({ id: `diff:${change.path}`, name: change.path, type: 'diff', createdAt: Date.now(), storageRef: change.path })}
            onDecide={onDecide}
            onOpenRun={openRun}
          />
        )}

        {viewing && (
          <div className="absolute inset-0 z-20 flex flex-col bg-background/85 backdrop-blur-sm">
            <ArtifactViewer artifact={viewing} load={loadArtifact} onClose={() => setViewing(null)} />
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

function PanelBody({
  panel,
  state,
  nowMs,
  runId,
  onOpenArtifact,
  onOpenDiff,
  onDecide,
  onOpenRun,
}: {
  panel: WorkspacePanel;
  state: AgentWorkspaceState;
  nowMs: number;
  runId: string | null;
  onOpenArtifact: (a: ArtifactRef) => void;
  onOpenDiff: (c: import('@/lib/agent-workspace/types').FileChange) => void;
  onDecide: (id: string, approve: boolean) => Promise<void>;
  onOpenRun: (id: string) => void;
}) {
  switch (panel) {
    case 'overview':
      return <OverviewPanel state={state} nowMs={nowMs} />;
    case 'activity':
      return <ActivityPanel entries={state.activity} />;
    case 'tasks':
      return <TasksPanel tasks={state.tasks} />;
    case 'changes':
      return <ChangesPanel changes={state.changes} onOpenDiff={onOpenDiff} />;
    case 'context':
      return <ContextPanel context={state.context} sources={state.contextSources} />;
    case 'telemetry':
      return <TelemetryPanel telemetry={state.telemetry} model={state.model} nowMs={nowMs} />;
    case 'permissions':
      return <PermissionsPanel permissions={state.permissions} onDecide={onDecide} />;
    case 'artifacts':
      return <ArtifactsPanel artifacts={state.artifacts} onOpen={onOpenArtifact} />;
    case 'terminal':
      return <ArtifactsPanel artifacts={state.artifacts.filter((a) => a.type === 'terminal')} onOpen={onOpenArtifact} />;
    case 'research':
      return <ResearchPanel research={state.research} />;
    case 'browser':
      return <BrowserPanel browser={state.browser} />;
    case 'computer':
      return <ComputerPanel computer={state.computer} />;
    case 'history':
      return <HistoryPanel onOpenRun={onOpenRun} activeRunId={runId} />;
    default:
      return null;
  }
}

/** A small, accessible toggle used by the shell header. */
export function AgentWorkspaceToggle({ className }: { className?: string }) {
  const open = useWorkspaceStore((s) => s.open);
  const toggle = useWorkspaceStore((s) => s.toggle);
  const t = useT();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={t('workspace.open')}
      aria-pressed={open}
      title={t('workspace.open')}
      className={cn(
        'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors',
        open ? 'bg-white/[0.08] text-primary' : 'text-muted-foreground/70 hover:bg-accent hover:text-foreground',
        className,
      )}
    >
      <Sparkles size={18} />
    </button>
  );
}
