'use client';

// ── useMediaQuery — the one viewport-breakpoint hook ─────────────────────────
// Consolidates the ad-hoc `window.matchMedia` calls that had spread across the
// Agent Workspace, the workspace canvas, the market workspace and the calendars.
// SSR-safe: returns `false` until the client mounts, then tracks the real match.

import { useEffect, useState } from 'react';

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia(query);
    const update = () => setMatches(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [query]);
  return matches;
}

/** Width thresholds that mirror Tailwind's `md` and `lg` breakpoints. */
export const MOBILE_QUERY = '(max-width: 767px)';
export const TABLET_QUERY = '(min-width: 768px) and (max-width: 1023px)';
export const DESKTOP_QUERY = '(min-width: 1024px)';

/** True below `md` (< 768px): phones, and the layout that must stack. */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_QUERY);
}

/** True at `lg` and up (>= 1024px): side columns sit beside the content again. */
export function useIsDesktop(): boolean {
  return useMediaQuery(DESKTOP_QUERY);
}
