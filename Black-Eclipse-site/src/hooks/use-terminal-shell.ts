'use client';

import { useEffect } from 'react';
import { hydrateTerminalStore, useTerminalStore } from '@/lib/terminal/store';

/**
 * Wire the terminal dock into the app shell:
 *
 *   * hydrate the persisted open state / placement once on the client, so the
 *     docked regions reserve their space on first paint without a mismatch;
 *   * tuck the terminal away in focus mode, where the shell is intentionally bare.
 */
export function useTerminalShell(focusMode: boolean): void {
  const open = useTerminalStore((s) => s.open);
  useEffect(() => {
    hydrateTerminalStore();
  }, []);
  useEffect(() => {
    if (focusMode && open) useTerminalStore.getState().setOpen(false);
  }, [focusMode, open]);
}
