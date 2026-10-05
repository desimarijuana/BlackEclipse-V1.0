'use client';

import { useState } from 'react';
import { Terminal as TerminalIcon } from '@/lib/icons';
import { XtermTerminal } from '@/components/terminal/xterm-terminal';

/**
 * The body of a standalone terminal window (`/terminal?session=…`).
 *
 * When a session id is present it attaches to that running shell; otherwise it
 * opens a fresh one owned by this window, so a pop-out always works even without
 * one. The whole viewport is the terminal.
 */
export function TerminalWindow({ sessionId, shell }: { sessionId: string | null; shell: string | null }) {
  // A per-window owner for the "no session id" case, so each window gets its own.
  const [owner] = useState(
    () => `terminal-window-${Math.random().toString(36).slice(2, 10)}`,
  );
  const [title, setTitle] = useState(shell ?? 'shell');

  return (
    <div className="flex h-[100dvh] w-full flex-col bg-background text-foreground">
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
        <TerminalIcon size={12} />
        <span className="text-emerald-300">{title}</span>
        <span>{sessionId ? `session ${sessionId}` : 'new session'}</span>
        <span className="ml-auto">Eclipse Terminal</span>
      </div>
      <div className="min-h-0 flex-1 p-2">
        <XtermTerminal
          sessionId={sessionId ?? undefined}
          owner={sessionId ? undefined : owner}
          shell={shell ?? undefined}
          fill
          onSession={(info) => setTitle(info.shell)}
        />
      </div>
    </div>
  );
}
