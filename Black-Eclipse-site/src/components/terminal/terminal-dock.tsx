'use client';

import { useState } from 'react';
import {
  Activity,
  Columns3,
  List,
  Maximize2,
  Minimize2,
  Network,
  Plus,
  Square,
  Terminal as TerminalIcon,
  X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { ProcessPanel } from '@/components/terminal/process-panel';
import { PortPanel } from '@/components/terminal/port-panel';
import { XtermTerminal } from '@/components/terminal/xterm-terminal';
import { useTerminalStore, type TerminalPlacement } from '@/lib/terminal/store';

type View = 'terminal' | 'processes' | 'ports';

//: A stable per-browser terminal id, so reopening reattaches to the SAME shell.
function terminalOwner(): string {
  if (typeof window === 'undefined') return 'terminal-ui';
  try {
    const existing = window.localStorage.getItem('eclipse-terminal-owner');
    if (existing) return existing;
    const created = `terminal-ui-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem('eclipse-terminal-owner', created);
    return created;
  } catch {
    return 'terminal-ui';
  }
}

const PLACEMENT_OPTIONS: Array<{ id: TerminalPlacement; label: string; icon: typeof List }> = [
  { id: 'bottom', label: 'Dock to bottom', icon: List },
  { id: 'right', label: 'Dock to right', icon: Columns3 },
  { id: 'full', label: 'Full page', icon: Square },
];

/**
 * The terminal as a REAL docked region, not a floating overlay.
 *
 * `slot` is where the app shell placed this instance in its layout:
 *   * `bottom` — a strip inside the main column, below the page content.
 *   * `right`  — a full-height column beside the main panel.
 *   * `full`   — the whole window.
 * Only the instance whose slot matches the chosen placement renders, so the
 * layout reserves space for it and the app never overlaps it.
 */
export function TerminalDock({ slot }: { slot: TerminalPlacement }) {
  const open = useTerminalStore((s) => s.open);
  const placement = useTerminalStore((s) => s.placement);
  const generation = useTerminalStore((s) => s.generation);
  const setOpen = useTerminalStore((s) => s.setOpen);
  const setPlacement = useTerminalStore((s) => s.setPlacement);
  const newShell = useTerminalStore((s) => s.newShell);
  const [view, setView] = useState<View>('terminal');
  const [baseOwner] = useState(() => terminalOwner());
  const activeOwner = `${baseOwner}-${generation}`;

  if (!open || placement !== slot) return null;

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
        isRight ? 'h-full w-[26rem] shrink-0 border-l' : '',
        slot === 'bottom' ? 'h-80 w-full shrink-0 border-t' : '',
      )}
    >
      <div className="flex items-center justify-between gap-2 px-3 py-1.5">
        <div className="flex min-w-0 items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setView(tab.id)}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs transition',
                view === tab.id ? 'bg-white/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <tab.icon size={13} /> <span className="hidden sm:inline">{tab.label}</span>
            </button>
          ))}
          {view === 'terminal' ? (
            <button
              type="button"
              onClick={newShell}
              title="Open a new shell"
              className="ml-1 flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <Plus size={11} /> <span className="hidden md:inline">New</span>
            </button>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <div className="mr-1 flex items-center rounded-lg bg-white/[0.04] p-0.5">
            {PLACEMENT_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setPlacement(opt.id)}
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
          {!isFull ? (
            <button
              type="button"
              onClick={() => setPlacement('full')}
              aria-label="Full page"
              title="Full page"
              className="text-muted-foreground hover:text-foreground"
            >
              <Maximize2 size={14} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setPlacement('bottom')}
              aria-label="Restore terminal size"
              title="Restore"
              className="text-muted-foreground hover:text-foreground"
            >
              <Minimize2 size={14} />
            </button>
          )}
          <button type="button" onClick={() => setOpen(false)} aria-label="Close terminal" className="text-muted-foreground hover:text-foreground">
            <X size={14} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 px-3 pb-3">
        {view === 'processes' ? (
          <ProcessPanel />
        ) : view === 'ports' ? (
          <PortPanel />
        ) : (
          <XtermTerminal key={activeOwner} owner={activeOwner} fill />
        )}
      </div>
    </div>
  );
}
