'use client';

// Warm the Graph-mode screens while the shell is idle. Their chunks are large
// (React Flow / node library); without this the first click on Workflows sits on
// the slim top loader for a long time and reads as a broken page.

import { useEffect } from 'react';

export function GraphScreenPrefetch() {
  useEffect(() => {
    let idleId: number | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const prefetch = () => {
      void import('@/components/screens/overview/overview-screen');
      void import('@/components/screens/tables/tables-screen');
    };
    if (typeof window.requestIdleCallback === 'function') {
      idleId = window.requestIdleCallback(prefetch, { timeout: 4000 });
    } else {
      timer = setTimeout(prefetch, 2500);
    }
    return () => {
      if (idleId !== null && typeof window.cancelIdleCallback === 'function') window.cancelIdleCallback(idleId);
      if (timer) clearTimeout(timer);
    };
  }, []);
  return null;
}
