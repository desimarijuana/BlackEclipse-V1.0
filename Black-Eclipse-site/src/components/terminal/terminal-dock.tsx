'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  ArrowDownToLine,
  Columns3,
  List,
  Maximize2,
  Minimize2,
  Network,
  Plus,
  Square,
  SquareArrowOutUpRight,
  Terminal as TerminalIcon,
  X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { ProcessPanel } from '@/components/terminal/process-panel';
import { PortPanel } from '@/components/terminal/port-panel';
import { XtermTerminal } from '@/components/terminal/xterm-terminal';
import { useTerminalStore, terminalOwnerId, type TerminalPlacement } from '@/lib/terminal/store';

type View = 'terminal' | 'processes' | 'ports';

const PLACEMENT_OPTIONS: Array<{ id: TerminalPlacement; label: string; icon: typeof List }> = [
  { id: 'bottom', label: 'Dock to bottom', icon: List },
  { id: 'right', label: 'Dock to right', icon: Columns3 },
  { id: 'full', label: 'Full page', icon: Square },
];

/** A draggable, floating terminal detached from the layout. */
function TerminalPopout({
  sessionId,
  shell,
  onDockBack,
}: {
  sessionId?: string;
  shell?: string;
  onDockBack: () => void;
}) {
  const [pos, setPos] = useState<{ x: number; y: number }>(() => ({
    x: typeof window === 'undefined' ? 80 : Math.max(24, window.innerWidth - 780),
    y: 96,
  }));
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);

  const onPointerDown = (e: React.PointerEvent) => {
    dragRef.current = { dx: e.clientX - pos.x, dy: e.clientY - pos.y };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    setPos({
      x: Math.min(Math.max(0, e.clientX - dragRef.current.dx), window.innerWidth - 120),
      y: Math.min(Math.max(0, e.clientY - dragRef.current.dy), window.innerHeight - 60),
    });
  };
  const onPointerUp = () => {
    dragRef.current = null;
  };

  return (
    <div
      className="fixed z-[95] flex h-[26rem] w-[min(46rem,90vw)] flex-col overflow-hidden rounded-2xl border border-white/15 bg-background/95 shadow-2xl backdrop-blur-xl"
      style={{ left: pos.x, top: pos.y, resize: 'both' }}
    >
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className="flex cursor-move items-center justify-between gap-2 border-b border-white/10 px-3 py-1.5"
      >
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <TerminalIcon size={12} /> Terminal (detached)
        </span>
        <div className="flex items-center gap-1">
          <button type="button" onClick={onDockBack} title="Dock back" aria-label="Dock terminal back" className="text-muted-foreground hover:text-foreground">
            <ArrowDownToLine size={13} />
          </button>
          <button type="button" onClick={() => sessionId && window.open(`/terminal?session=${encodeURIComponent(sessionId)}`, 'eclipse-terminal-window', 'width=1000,height=650')} title="Open in a new window" aria-label="Open terminal in a new window" className="text-muted-foreground hover:text-foreground">
            <SquareArrowOutUpRight size={13} />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 p-1">
        <XtermTerminal sessionId={sessionId} shell={shell} fill />
      </div>
    </div>
  );
}

/**
 * The terminal as a REAL docked region, not a floating overlay.
 *
 * `slot` is where the app shell placed this instance in its layout:
 *   * `bottom` — a strip inside the main column, below the page content.
 *   * `right`  — a full-height column beside the main panel (collapses to a strip
 *     on narrow screens, where a side column would overlap).
 *   * `full`   — the whole window.
 * Only the instance whose slot matches the chosen placement renders, so the
 * layout reserves space for it and the app never overlaps it. A detached terminal
 * renders as a floating pop-out instead, freeing the docked space.
 */
export function TerminalDock({ slot }: { slot: TerminalPlacement }) {
  const open = useTerminalStore((s) => s.open);
  const placement = useTerminalStore((s) => s.placement);
  const generation = useTerminalStore((s) => s.generation);
  const setOpen = useTerminalStore((s) => s.setOpen);
  const setPlacement = useTerminalStore((s) => s.setPlacement);
  const newShell = useTerminalStore((s) => s.newShell);
  const [view, setView] = useState<View>('terminal');
  const [detached, setDetached] = useState(false);
  const [session, setSession] = useState<{ sessionId: string; shell: string } | null>(null);
  const baseOwner = useRef<string>(terminalOwnerId());
  const activeOwner = `${baseOwner.current}-${generation}`;

  const onSession = useCallback((info: { sessionId: string; shell: string }) => setSession(info), []);

  if (!open || placement !== slot) return null;

  // A detached terminal floats; it does not reserve docked space.
  if (detached && view === 'terminal') {
    return (
      <TerminalPopout
        sessionId={session?.sessionId}
        shell={session?.shell}
        onDockBack={() => setDetached(false)}
      />
    );
  }

  const tabs: Array<{ id: View; label: string; icon: typeof TerminalIcon }> = [
    { id: 'terminal', label: 'Terminal', icon: TerminalIcon },
    { id: 'processes', label: 'Processes', icon: Activity },
    { id: 'ports', label: 'Ports', icon: Network },
  ];

  const isFull = slot === 'full';
  const isRight = slot === 'right';

  return (
    <div
      role="region"
      aria-label="Terminal"
      className={cn(
        'flex flex-col overflow-hidden',
        // A docked region reserves its own space; only full-page floats, because
        // there nothing else is visible behind it.
        isFull
          ? 'fixed inset-0 z-[90] bg-background/95 backdrop-blur-xl p-3'
          : 'relative z-20 border-white/10 bg-black/25 backdrop-blur-md',
        // The right column only on desktop; on narrow screens it becomes a strip,
        // so it can never sit on top of the main panel.
        isRight
          ? 'h-64 w-full shrink-0 border-t md:h-full md:w-[24rem] md:border-t-0 md:border-l lg:w-[26rem]'
          : '',
        slot === 'bottom' ? 'h-72 w-full shrink-0 border-t' : '',
      )}
    >
      {/* Header wraps instead of overlapping when the dock is narrow. */}
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 px-2 py-1.5 sm:px-3">
        <div className="flex min-w-0 items-center gap-0.5">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setView(tab.id)}
              title={tab.label}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs transition',
                view === tab.id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <tab.icon size={13} />
              {/* Labels only when there is room: the icon is always present and
                  the title carries the meaning at narrow widths. */}
              <span className="hidden xl:inline">{tab.label}</span>
            </button>
          ))}
          {view === 'terminal' ? (
            <button
              type="button"
              onClick={newShell}
              title="Open a new shell"
              className="ml-0.5 flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <Plus size={11} /> <span className="hidden xl:inline">New</span>
            </button>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          {/* Placement: dock bottom / dock right / full page. */}
          <div className="flex items-center rounded-lg bg-white/[0.04] p-0.5">
            {PLACEMENT_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => {
                  setDetached(false);
                  setPlacement(opt.id);
                }}
                title={opt.label}
                aria-label={opt.label}
                aria-pressed={placement === opt.id}
                className={cn(
                  'flex h-6 w-6 items-center justify-center rounded-md transition-colors',
                  placement === opt.id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <opt.icon size={13} />
              </button>
            ))}
          </div>
          {view === 'terminal' ? (
            <button
              type="button"
              onClick={() => setDetached(true)}
              disabled={!session}
              title="Detach as a pop-out"
              aria-label="Detach terminal"
              className="flex h-6 w-6 items-center justify-center text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
            >
              <SquareArrowOutUpRight size={13} />
            </button>
          ) : null}
          {!isFull ? (
            <button
              type="button"
              onClick={() => setPlacement('full')}
              aria-label="Full page"
              title="Full page"
              className="flex h-6 w-6 items-center justify-center text-muted-foreground hover:text-foreground"
            >
              <Maximize2 size={13} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setPlacement('bottom')}
              aria-label="Restore terminal size"
              title="Restore"
              className="flex h-6 w-6 items-center justify-center text-muted-foreground hover:text-foreground"
            >
              <Minimize2 size={13} />
            </button>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close terminal"
            title="Close"
            className="flex h-6 w-6 items-center justify-center text-muted-foreground hover:text-foreground"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 px-2 pb-2 sm:px-3 sm:pb-3">
        {view === 'processes' ? (
          <ProcessPanel />
        ) : view === 'ports' ? (
          <PortPanel />
        ) : (
          <XtermTerminal key={activeOwner} owner={activeOwner} fill onSession={onSession} />
        )}
      </div>
    </div>
  );
}
