'use client';

// Closed-by-default shell chrome, split out of `stock-chat.tsx` so the page
// stays under its size ratchet and each module loads only when it is needed:
// the terminal (xterm), the Bots scheduler, the floating assistant, and the
// decorative WebGL Aurora (which also waits for the shell to hydrate).

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';

export const TerminalDock = dynamic(
  () => import('@/components/terminal/terminal-dock').then((m) => m.TerminalDock),
  { ssr: false },
);
export const BotSchedulerDock = dynamic(
  () => import('@/components/bots/scheduler-dock').then((m) => m.BotSchedulerDock),
  { ssr: false },
);
export const ChatDock = dynamic(
  () => import('@/components/chat/chat-dock').then((m) => m.ChatDock),
  { ssr: false },
);

const AuroraGlow = dynamic(
  () => import('@/components/layout/aurora-glow').then((m) => m.AuroraGlow),
  { ssr: false },
);

/** The Aurora shader engine loads after the shell is interactive. */
export function DeferredAurora({ className }: { className?: string }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setReady(true), 1_200);
    return () => clearTimeout(timer);
  }, []);
  return ready ? <AuroraGlow className={className} /> : null;
}
