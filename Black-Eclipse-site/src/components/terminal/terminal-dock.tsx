'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  AppWindow,
  Boxes,
  Cloud,
  Columns3,
  CornersIn,
  CornersOut,
  Cpu,
  Export,
  Network,
  Plus,
  Rows3,
  Terminal as TerminalIcon,
  X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { ProcessPanel } from '@/components/terminal/process-panel';
import { PortPanel } from '@/components/terminal/port-panel';
import { ApplicationRuntimePanel } from '@/components/terminal/runtime-panel';
import { ProviderReadinessPanel } from '@/components/terminal/provider-panel';
import { XtermTerminal } from '@/components/terminal/xterm-terminal';
import { useTerminalStore, terminalOwnerId, type TerminalPlacement } from '@/lib/terminal/store';

type View = 'terminal' | 'processes' | 'ports' | 'applications' | 'providers';

const PLACEMENT_OPTIONS: Array<{ id: TerminalPlacement; label: string; icon: typeof Columns3 }> = [
  { id: 'bottom', label: 'Dock to bottom', icon: Rows3 },
  { id: 'right', label: 'Dock to right', icon: Columns3 },
  { id: 'full', label: 'Full page', icon: CornersOut },
];

/** A draggable, resizable, floating terminal, portaled so its glass samples the page. */
function TerminalPopout({
  sessionId,
  shell,
  onDockBack,
}: {
  sessionId?: string;
  shell?: string;
  onDockBack: () => void;
}) {
  const MIN_W = 360;
  const MIN_H = 220;
  const [mounted, setMounted] = useState(false);
  const [geom, setGeom] = useState(() => ({
    x: typeof window === 'undefined' ? 80 : Math.max(24, Math.round((window.innerWidth - 760) / 2)),
    y: 72,
    w: 760,
    h: 440,
  }));
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);
  const resizeRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);

  useEffect(() => setMounted(true), []);

  // Keep it on-screen if the viewport shrinks.
  useEffect(() => {
    const clamp = () =>
      setGeom((g) => ({
        x: Math.min(g.x, Math.max(0, window.innerWidth - 80)),
        y: Math.min(g.y, Math.max(0, window.innerHeight - 40)),
        w: Math.min(g.w, window.innerWidth - 16),
        h: Math.min(g.h, window.innerHeight - 16),
      }));
    window.addEventListener('resize', clamp);
    return () => window.removeEventListener('resize', clamp);
  }, []);

  const startDrag = (e: React.PointerEvent) => {
    dragRef.current = { dx: e.clientX - geom.x, dy: e.clientY - geom.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const moveDrag = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    setGeom((g) => ({
      ...g,
      x: Math.min(Math.max(0, e.clientX - dragRef.current!.dx), window.innerWidth - 80),
      y: Math.min(Math.max(0, e.clientY - dragRef.current!.dy), window.innerHeight - 40),
    }));
  };

  const startResize = (e: React.PointerEvent) => {
    e.stopPropagation();
    resizeRef.current = { x: e.clientX, y: e.clientY, w: geom.w, h: geom.h };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const moveResize = (e: React.PointerEvent) => {
    if (!resizeRef.current) return;
    const r = resizeRef.current;
    setGeom((g) => ({
      ...g,
      w: Math.max(MIN_W, Math.min(r.w + (e.clientX - r.x), window.innerWidth - g.x - 8)),
      h: Math.max(MIN_H, Math.min(r.h + (e.clientY - r.y), window.innerHeight - g.y - 8)),
    }));
  };
  const endPointer = () => {
    dragRef.current = null;
    resizeRef.current = null;
  };

  if (!mounted) return null;

  return createPortal(
    <div
      role="region"
      aria-label="Terminal (detached)"
      // `glass-card-strong` gives the frosted blur; portaled to <body> so it isn't
      // scoped inside a transformed/backdrop-root ancestor.
      className="glass-card-strong fixed z-[100] flex flex-col overflow-hidden rounded-2xl border border-white/12 shadow-2xl"
      style={{ left: geom.x, top: geom.y, width: geom.w, height: geom.h }}
    >
      <div
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
        className="flex cursor-move touch-none select-none items-center justify-between gap-2 border-b border-white/10 px-3 py-1.5"
      >
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <TerminalIcon size={12} /> Terminal
        </span>
        <div className="flex items-center gap-0.5">
          <button type="button" onClick={onDockBack} title="Dock back into the layout" aria-label="Dock terminal back" className="flex h-6 w-6 items-center justify-center text-muted-foreground hover:text-foreground">
            <CornersIn size={13} />
          </button>
          <button
            type="button"
            onClick={() => sessionId && window.open(`/terminal?session=${encodeURIComponent(sessionId)}`, 'eclipse-terminal-window', 'width=1000,height=650')}
            title="Open in a new window"
            aria-label="Open terminal in a new window"
            className="flex h-6 w-6 items-center justify-center text-muted-foreground hover:text-foreground"
          >
            <AppWindow size={13} />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 p-1">
        <XtermTerminal sessionId={sessionId} shell={shell} fill />
      </div>
      {/* Resize handle (bottom-right). Pointer-driven, so it works inside a portal. */}
      <div
        onPointerDown={startResize}
        onPointerMove={moveResize}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
        aria-label="Resize terminal"
        title="Resize"
        className="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize touch-none"
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4 text-muted-foreground/60">
          <path d="M15 6 L6 15 M15 11 L11 15" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
        </svg>
      </div>
    </div>,
    document.body,
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
  // Docked size, draggable on the inner edge: the bottom dock's height and the
  // right dock's width. Defaults match the old fixed classes.
  const [bottomH, setBottomH] = useState(288);
  const [rightW, setRightW] = useState(384);
  const resizeRef = useRef<{ x: number; y: number; h: number; w: number } | null>(null);
  const baseOwner = useRef<string>(terminalOwnerId());
  const activeOwner = `${baseOwner.current}-${generation}`;

  const onSession = useCallback((info: { sessionId: string; shell: string }) => setSession(info), []);

  const startDockResize = (e: React.PointerEvent) => {
    resizeRef.current = { x: e.clientX, y: e.clientY, h: bottomH, w: rightW };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const moveDockResize = (e: React.PointerEvent) => {
    const r = resizeRef.current;
    if (!r) return;
    if (slot === 'bottom') setBottomH(Math.max(140, Math.min(r.h - (e.clientY - r.y), window.innerHeight - 160)));
    if (slot === 'right') setRightW(Math.max(260, Math.min(r.w - (e.clientX - r.x), window.innerWidth - 320)));
  };
  const endDockResize = () => {
    resizeRef.current = null;
  };

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
    { id: 'processes', label: 'Processes', icon: Cpu },
    { id: 'ports', label: 'Ports', icon: Network },
    { id: 'applications', label: 'Applications', icon: Boxes },
    { id: 'providers', label: 'Providers', icon: Cloud },
  ];

  const isFull = slot === 'full';
  const isRight = slot === 'right';

  return (
    <div
      role="region"
      aria-label="Terminal"
      className={cn(
        'flex flex-col overflow-hidden',
        // Frosted glass, matching the app's design system. The tint is translucent
        // and the blur is strong, so the page shows through, blurred.
        'glass-card-strong',
        // Only full-page floats; the docked slots reserve their own space.
        isFull ? 'fixed inset-0 z-[90] p-3' : 'relative z-20 border-white/10',
        // The right column only on desktop; on narrow screens it becomes a strip,
        // so it can never sit on top of the main panel.
        isRight
          ? 'h-64 w-full shrink-0 border-t md:h-full md:border-t-0 md:border-l'
          : '',
        slot === 'bottom' ? 'w-full shrink-0 border-t' : '',
      )}
      style={
        slot === 'bottom'
          ? { height: bottomH }
          : isRight
            ? { width: rightW, height: '100%' }
            : undefined
      }
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
              <Export size={13} />
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
              <CornersOut size={13} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setPlacement('bottom')}
              aria-label="Restore terminal size"
              title="Restore"
              className="flex h-6 w-6 items-center justify-center text-muted-foreground hover:text-foreground"
            >
              <CornersIn size={13} />
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
        ) : view === 'applications' ? (
          <ApplicationRuntimePanel />
        ) : view === 'providers' ? (
          <ProviderReadinessPanel />
        ) : (
          <XtermTerminal key={activeOwner} owner={activeOwner} fill onSession={onSession} />
        )}
      </div>

      {/* Drag the inner edge to resize the docked panel (bottom: height,
          right: width). Hidden on the full-page slot, which already fills the
          window, and on the right slot's narrow (stacked) layout. */}
      {!isFull ? (
        <div
          onPointerDown={startDockResize}
          onPointerMove={moveDockResize}
          onPointerUp={endDockResize}
          onPointerCancel={endDockResize}
          aria-label="Resize terminal dock"
          title="Drag to resize"
          className={cn(
            'absolute touch-none',
            slot === 'bottom'
              ? 'inset-x-0 top-0 h-1.5 cursor-ns-resize'
              : 'hidden md:block md:inset-y-0 md:left-0 md:w-1.5 md:cursor-ew-resize',
          )}
        />
      ) : null}
    </div>
  );
}
