'use client';

import { useEffect, useRef } from 'react';

/**
 * A `setInterval` that only runs while its tab is ACTIVE and the page is
 * visible. The shell keeps visited screens mounted behind `hidden`, so a plain
 * interval kept polling every hidden screen forever. Use this for any list or
 * status refresh inside a keep-alive tab.
 */
export function useActiveInterval(active: boolean, callback: () => void, ms: number): void {
  const cb = useRef(callback);
  cb.current = callback;

  useEffect(() => {
    if (!active) return;
    const tick = () => {
      if (!document.hidden) cb.current();
    };
    const timer = setInterval(tick, ms);
    return () => clearInterval(timer);
  }, [active, ms]);
}
