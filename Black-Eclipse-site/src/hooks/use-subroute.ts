// ── useSubroute ─────────────────────────────────────────────────────────────
// Lets a keep-alive screen react to a `Destination.subroute` dispatched by the
// global search palette (e.g. `economics.calendar`, `journal.analytics`,
// `alerts.create`). The shell publishes the request via
// `useCommandStore.requestSubroute(tab, subroute, focus)`; the screen owning
// `tab` subscribes here and applies it.
//
// A subscription (not a mount-time read) is required because the SPA keeps
// screens mounted with `display:none` — a tab revisit does not remount, so a
// one-shot prop would silently never fire a second time.

'use client';

import { useEffect, useRef } from 'react';
import { useCommandStore } from '@/lib/search/store';

export interface SubrouteRequest {
  /** Full subroute string, e.g. 'economics.calendar'. */
  subroute: string;
  /** Optional focus target within the sub-view, e.g. 'NFP'. */
  focus?: string;
}

/**
 * Subscribe to subroute requests for `tab` only.
 *
 * @param tab     The owning tab id (must match the dispatched `Destination.tab`).
 * @param handler Called with the request. It is kept in a ref, so an inline
 *   closure is fine and is always the latest version when a request arrives.
 *   Pass `null` to ignore requests.
 */
export function useSubroute(
  tab: string,
  handler: ((req: SubrouteRequest) => void) | null,
): void {
  const ref = useRef(handler);
  ref.current = handler;
  const enabled = handler !== null;

  useEffect(() => {
    if (!enabled) return;
    const dispatch = () => {
      const req = useCommandStore.getState().pendingSubroute;
      if (req && req.tab === tab) {
        ref.current?.({ subroute: req.subroute, focus: req.focus });
        useCommandStore.getState().clearSubroute(tab);
      }
    };
    // Apply a request that arrived before this screen mounted.
    dispatch();
    const unsub = useCommandStore.subscribe((state, prev) => {
      if (state.pendingSubroute !== prev.pendingSubroute && state.pendingSubroute?.tab === tab) {
        dispatch();
      }
    });
    return unsub;
  }, [tab, enabled]);
}
