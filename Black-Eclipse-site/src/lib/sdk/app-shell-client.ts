'use client';

// ── App shell live sync ──────────────────────────────────────────────────────
// Mounted once (via UiCatalogSync). Subscribes to `/api/sdk/app/stream`, applies
// app-wide nav changes to the sidebar store and opens navigation commands from
// chat/Python. If SSE is unavailable, a slow poll still converges the nav.

import { useEffect } from 'react';
import { useSidebarConfigStore } from '@/lib/sidebar/store';
import { eclipseSdk } from './index';
import type { AppNavigateTarget, AppShellState } from './app-shell-types';
import { navigateTo } from './navigate';

const POLL_MS = 30_000;

export function useAppShellSync(): void {
  useEffect(() => {
    const store = useSidebarConfigStore.getState();
    if (!store.hydrated) store.hydrate();

    let source: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let closed = false;

    const applyNav = (state: AppShellState) => {
      if (!state || !state.initialized) return;
      useSidebarConfigStore.getState().applyRemoteState(state);
    };

    const refresh = async () => {
      try {
        const state = await eclipseSdk.app.get();
        if (!closed) applyNav(state);
      } catch {
        /* the runtime/DB is unavailable — the local cache stays usable */
      }
    };

    const startPoll = () => {
      if (poll || closed) return;
      poll = setInterval(() => void refresh(), POLL_MS);
    };

    try {
      source = new EventSource('/api/sdk/app/stream');
      source.addEventListener('nav', (event) => {
        try {
          applyNav(JSON.parse((event as MessageEvent).data) as AppShellState);
        } catch {
          /* ignore a malformed frame */
        }
      });
      source.addEventListener('navigate', (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent).data) as { target?: AppNavigateTarget };
          if (payload.target) navigateTo(payload.target);
        } catch {
          /* ignore a malformed frame */
        }
      });
      source.addEventListener('error', startPoll);
    } catch {
      startPoll();
    }

    void refresh();
    return () => {
      closed = true;
      source?.close();
      if (poll) clearInterval(poll);
    };
  }, []);
}
