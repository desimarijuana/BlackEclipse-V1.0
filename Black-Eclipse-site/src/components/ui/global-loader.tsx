'use client';

import { useEffect, useRef, useState } from 'react';
import { AsciiProgress } from '@/components/ui/ascii-loader';
import { getBootProgress, subscribeBootProgress, installBootFetchTracking } from '@/lib/fetch-progress';

// Real warm-up endpoints fetched while the overlay is up. Each one counts
// toward the percentage, so "% loading markets" reflects actual data that
// the app will reuse (the routes cache their payloads, so the screens get
// them instantly after the overlay fades).
const WARMUP_ENDPOINTS = [
  '/api/markets',
  '/api/indices?market=US',
  '/api/global-overview',
  '/api/news?page=1&limit=10',
  '/api/forex',
  '/api/commodities',
];

// Single full-page loader shown once during the initial app mount.
// The percentage counts up from 1 → 100 in a steady, visible climb while
// data loads: elapsed time guarantees the number keeps moving, and the real
// fetch ratio pulls it ahead when endpoints resolve early. Hides the moment
// all warm-up requests settle, or after maxDelay as a safety cap.
//
// It is deliberately NON-BLOCKING: `pointer-events-none` lets clicks pass
// through to the shell beneath (so the app is usable the instant it mounts)
// and it sits BELOW dialogs in z-order, so a dialog opened during the boot
// window renders on top of it instead of being hidden behind it. maxDelay is
// short because warm-ups are fire-and-forget: the screens fetch again on
// their own and their routes cache, so lingering adds no value.
export function GlobalLoader({ maxDelay = 2500 }: { maxDelay?: number }) {
  const [visible, setVisible] = useState(true);
  const [pct, setPct] = useState(1);
  const totalRef = useRef(getBootProgress().total);
  const doneRef = useRef(getBootProgress().done);

  // Patch window.fetch once so every API call during boot advances the tracker.
  useEffect(() => {
    const uninstall = installBootFetchTracking();
    const unsubscribe = subscribeBootProgress((s) => {
      totalRef.current = s.total;
      doneRef.current = s.done;
    });
    return () => {
      unsubscribe();
      uninstall();
    };
  }, []);

  // Fire the warm-up requests (fire-and-forget; the tracker in
  // fetch-progress updates done/total as each settles). Each gets a hard
  // abort timeout so a stalled endpoint can never leave the tracker (or the
  // loader) hanging, and rejections are swallowed — warm-up failures must
  // never surface as console errors.
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), maxDelay);
    for (const url of WARMUP_ENDPOINTS) {
      fetch(url, { signal: controller.signal }).catch(() => {});
    }
    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [maxDelay]);

  // Guaranteed count-up: every 120ms bump the percentage by at least one
  // step so the number visibly climbs 1 → 100 over maxDelay, while the real
  // fetch ratio can push it forward faster when endpoints resolve early.
  useEffect(() => {
    const start = performance.now();
    const id = setInterval(() => {
      const elapsed = performance.now() - start;
      const timePct = Math.min(99, Math.round((elapsed / maxDelay) * 100));
      const realPct = totalRef.current > 0
        ? Math.round((doneRef.current / totalRef.current) * 100)
        : 0;
      setPct(Math.max(timePct, realPct));
    }, 120);
    return () => clearInterval(id);
  }, [maxDelay]);

  // Hide early once all warm-up requests have settled (jump to 100 first).
  useEffect(() => {
    const id = setInterval(() => {
      const total = totalRef.current;
      const done = doneRef.current;
      if (total >= WARMUP_ENDPOINTS.length && done >= WARMUP_ENDPOINTS.length) {
        setPct(100);
        setVisible(false);
      }
    }, 200);
    return () => clearInterval(id);
  }, []);

  // Force-hide after the max delay so the overlay can never trap the user.
  useEffect(() => {
    const t = setTimeout(() => setVisible(false), maxDelay);
    return () => clearTimeout(t);
  }, [maxDelay]);

  if (!visible) return null;

  const shown = Math.min(100, Math.max(1, pct));

  return (
    <div className="pointer-events-none fixed inset-0 z-40 flex flex-col items-center justify-center gap-5 bg-background/98 backdrop-blur-md" data-global-loader data-pct={Math.floor(shown)}>
       <AsciiProgress pct={shown} label="" size={32} />
    </div>
  );
}
