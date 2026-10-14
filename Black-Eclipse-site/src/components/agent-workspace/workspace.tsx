'use client';

// â”€â”€ Agent Workspace â€” the right sidebar (execution observability) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// A REAL docked column in the app shell's primary row (not a floating overlay):
// the main panel shrinks to make room, exactly like the terminal's right dock.
// It reflects what the agent is doing and â€” its default view â€” what it produced,
// with large outputs expanded inline, in the ChatGPT / Claude Code / Kimi idiom.
//
// Mounted in `stock-chat.tsx` as a sibling of the main column, so it reserves
// space and sits at full height. It reads the live normalized state from
// `useWorkspaceStore`, which is fed by the existing chat SSE stream. It owns no
// agent logic and never talks to the runtime except to replay a finished run's
// persisted trace.

import { useEffect, useMemo, useRef, useState } from 'react';
import { Bot, PanelRight, Sparkles, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/i18n/types';
import { useWorkspaceStore, hydrateWorkspaceStore, type WorkspacePanel } from '@/lib/agent-workspace/store';
import { fetchRunTrace, loadRunSnapshot } from '@/lib/agent-workspace/history';
import type { AgentWorkspaceState, ArtifactRef } from '@/lib/agent-workspace/types';
import { OutputPanel } from './output-panel';
import { ContextPanel } from './context-panel';
import { ChangesPanel } from './changes-panel';
import { PermissionsPanel } from './permissions-panel';
import { HistoryPanel } from './history-panel';
import { ExplainPanel } from './explain-panel';
import { ArtifactViewer, type LoadedContent } from './viewer';
import { PANEL_ICONS, statusIcon } from './ui';

// The sidebar is deliberately minimal: what the agent did (Output), how full the
// model's context window is (Context), what it changed (Changes), what it needs
// (Approvals) and past runs (History). The other telemetry/tasks/browser/computer
// detail views were removed — they read as noise here; the Output feed carries
// the useful signal.
const BASE_PANELS: readonly WorkspacePanel[] = ['context', 'output', 'changes', 'permissions', 'history'];

// "Influences" (memory/skill observability) is chat-run specific, so it is only
// offered while the ChatBot tab is in front (the caller passes `showExplain`).
const PANEL_KEY: Record<WorkspacePanel, TranslationKey> = {
  output: 'workspace.panel.output',
  context: 'workspace.panel.context',
  changes: 'workspace.panel.changes',
  permissions: 'workspace.panel.permissions',
  history: 'workspace.panel.history',
  explain: 'workspace.panel.explain',
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

const MIN_W = 300;
const MAX_W = 760;
const DEFAULT_W = 400;

function storeWidth(value: number): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem('black-eclipse:workspace-width', String(Math.round(value)));
  } catch {
    /* private mode */
  }
}
function readWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_W;
  try {
    const raw = window.localStorage.getItem('black-eclipse:workspace-width');
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) ? Math.min(MAX_W, Math.max(MIN_W, n)) : DEFAULT_W;
  } catch {
    return DEFAULT_W;
  }
}

/** Which panel shows a live "attention" dot (a pending decision owns it). */
function panelAttention(panel: WorkspacePanel, state: AgentWorkspaceState): boolean {
  if (panel === 'permissions') return state.permissions.some((p) => p.status === 'pending');
  if (panel === 'output') return state.execution.status === 'running' || state.execution.status === 'planning';
  return false;
}

export function AgentWorkspace({ showExplain = false }: { showExplain?: boolean }) {
  const open = useWorkspaceStore((s) => s.open);
  const state = useWorkspaceStore((s) => s.state);
  const activePanel = useWorkspaceStore((s) => s.activePanel);
  const runId = useWorkspaceStore((s) => s.runId);
  const setActivePanel = useWorkspaceStore((s) => s.setActivePanel);
  const setOpen = useWorkspaceStore((s) => s.setOpen);
  const t = useT();

  const [mounted, setMounted] = useState(false);
  const [viewing, setViewing] = useState<ArtifactRef | null>(null);
  const [width, setWidth] = useState(DEFAULT_W);
  const resizeRef = useRef<number | null>(null);

  useEffect(() => {
    setMounted(true);
    setWidth(readWidth());
    hydrateWorkspaceStore();
  }, []);

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
          const snapshot = await loadRunSnapshot(id);
          useWorkspaceStore.getState().loadRun(id, snapshot);
        } catch {
          useWorkspaceStore.getState().clear();
        }
      },
    [],
  );

  const startResize = (e: React.PointerEvent) => {
    resizeRef.current = e.clientX;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    if (typeof document !== 'undefined') {
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
    }
  };
  const moveResize = (e: React.PointerEvent) => {
    if (resizeRef.current == null) return;
    const next = Math.min(MAX_W, Math.max(MIN_W, width - (e.clientX - resizeRef.current)));
    resizeRef.current = e.clientX;
    setWidth(next);
  };
  const endResize = () => {
    if (resizeRef.current != null) storeWidth(width);
    resizeRef.current = null;
    if (typeof document !== 'undefined') {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  };

  if (!mounted || !open) return null;

  const panels: readonly WorkspacePanel[] = showExplain ? [...BASE_PANELS, 'explain'] : BASE_PANELS;
  const shownPanel = panels.includes(activePanel) ? activePanel : panels[0];

  const statusKey = STATUS_KEY[state.execution.status];

  return (
    <div
      role="complementary"
      aria-label={t('workspace.title')}
      style={{ width }}
      className={cn(
        // A real docked column beside the main panel: full height on desktop,
        // a full-width strip below the content on narrow screens (never an
        // overlay). Frosted glass per the Eclipse design system â€” no hard border
        // frame; the glass edge is the separation.
        'relative z-20 flex shrink-0 flex-col overflow-hidden',
        'glass-card-strong',
        'w-full md:h-full md:w-auto',
      )}
    >
      <header className="flex items-center gap-2 px-3 py-2">
        <Bot size={15} className="shrink-0 text-primary" />
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold text-foreground">
          {t('workspace.title')}
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[10.5px] text-muted-foreground/70">
          {statusIcon(state.execution.status, 11)}
          {t(statusKey)}
        </span>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label={t('workspace.close')}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-white/[0.06] hover:text-foreground"
        >
          <X size={13} />
        </button>
      </header>

      <nav aria-label={t('workspace.title')} className="flex shrink-0 flex-wrap items-center gap-0.5 px-2 py-1.5">
        {panels.map((panel) => {
          const attention = panelAttention(panel, state);
          const Icon = PANEL_ICONS[panel];
          return (
            <button
              key={panel}
              type="button"
              onClick={() => setActivePanel(panel)}
              aria-pressed={shownPanel === panel}
              className={cn(
                'relative flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] transition-colors',
                shownPanel === panel ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-foreground',
              )}
            >
              <Icon size={12} className="shrink-0" />
              {t(PANEL_KEY[panel])}
              {attention && <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-primary" />}
            </button>
          );
        })}
      </nav>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col p-3">
        {/* The panel body scrolls as a whole. Context (the default view) stacks
            a gauge, a 12-tile stat grid and the source list taller than the
            dock, and without this the lower context data was clipped by the
            column's `overflow-hidden`. Output keeps its own inner scroll. */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {!state.runId && state.activity.length === 0 && shownPanel !== 'history' ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <Sparkles size={20} className="text-muted-foreground/30" />
              <p className="text-[12px] leading-relaxed text-muted-foreground/50">{t('workspace.empty')}</p>
            </div>
          ) : (
            <PanelBody
              panel={shownPanel}
              state={state}
              runId={runId}
              load={loadArtifact}
              onOpenDiff={(change) => setViewing({ id: `diff:${change.path}`, name: change.path, type: 'diff', createdAt: Date.now(), storageRef: change.path })}
              onDecide={onDecide}
              onOpenRun={openRun}
            />
          )}
        </div>

        {viewing && (
          <div className="absolute inset-0 z-20 flex flex-col bg-background/85 backdrop-blur-sm">
            <ArtifactViewer artifact={viewing} load={loadArtifact} onClose={() => setViewing(null)} />
          </div>
        )}
      </div>

      {/* Drag the left edge to resize the docked column (desktop only). Sits
          above the content layer (z-30) so the whole edge is grabbable, with a
          hover affordance instead of a permanent border. */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={t('workspace.resize')}
        title={t('workspace.resize')}
        onPointerDown={startResize}
        onPointerMove={moveResize}
        onPointerUp={endResize}
        onPointerCancel={endResize}
        className="group absolute inset-y-0 left-0 z-30 hidden w-2 cursor-ew-resize touch-none select-none md:block"
      >
        <span className="pointer-events-none absolute inset-y-0 left-0 w-px bg-transparent transition-colors group-hover:bg-primary/40 group-active:bg-primary/60" />
      </div>
    </div>
  );
}

function PanelBody({
  panel,
  state,
  runId,
  load,
  onOpenDiff,
  onDecide,
  onOpenRun,
}: {
  panel: WorkspacePanel;
  state: AgentWorkspaceState;
  runId: string | null;
  load?: (artifact: ArtifactRef) => Promise<LoadedContent | null>;
  onOpenDiff: (c: import('@/lib/agent-workspace/types').FileChange) => void;
  onDecide: (id: string, approve: boolean) => Promise<void>;
  onOpenRun: (id: string) => void;
}) {
  switch (panel) {
    case 'output':
      return <OutputPanel activity={state.activity} artifacts={state.artifacts} load={load} />;
    case 'context':
      return (
        <ContextPanel
          context={state.context}
          sources={state.contextSources}
          telemetry={state.telemetry}
          model={state.model}
        />
      );
    case 'changes':
      return <ChangesPanel changes={state.changes} onOpenDiff={onOpenDiff} />;
    case 'permissions':
      return <PermissionsPanel permissions={state.permissions} onDecide={onDecide} />;
    case 'history':
      return <HistoryPanel onOpenRun={onOpenRun} activeRunId={runId} />;
    case 'explain':
      return <ExplainPanel runId={runId} />;
    default:
      return null;
  }
}

/** The header control that opens/closes the right sidebar. */
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
      <PanelRight size={18} />
    </button>
  );
}
