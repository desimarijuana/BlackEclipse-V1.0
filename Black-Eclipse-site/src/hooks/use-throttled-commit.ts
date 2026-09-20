"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Pure, framework-free rate limiter for high-frequency commits. Exposed so the
 * coalescing behavior can be unit-tested without a React renderer.
 *
 * Runs the first call immediately (leading edge), then coalesces the rest so
 * `commit` fires at most once per `intervalMs`, always with the latest value
 * (trailing edge). `flush` applies any pending value immediately.
 */
export function createThrottledCommit<T>(
  commit: (value: T) => void,
  intervalMs = 100,
  now: () => number = () => performance.now(),
  schedule: (fn: () => void, ms: number) => ReturnType<typeof setTimeout> = setTimeout,
  cancel: (handle: ReturnType<typeof setTimeout>) => void = clearTimeout,
) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending: { value: T } | null = null;
  // -Infinity so the very first emit is always applied immediately (leading
  // edge), regardless of the clock's starting point.
  let last = -Infinity;

  const flush = () => {
    if (timer != null) {
      cancel(timer);
      timer = null;
    }
    const next = pending;
    pending = null;
    if (next) {
      last = now();
      commit(next.value);
    }
  };

  const emit = (value: T) => {
    const elapsed = now() - last;
    if (elapsed >= intervalMs) {
      last = now();
      commit(value);
      return;
    }
    pending = { value };
    if (timer == null) {
      timer = schedule(flush, intervalMs - elapsed);
    }
  };

  /** Apply any pending value and drop the timer (used on unmount). */
  const dispose = () => {
    if (timer != null) {
      cancel(timer);
      timer = null;
    }
    if (pending) {
      commit(pending.value);
      pending = null;
    }
  };

  return { emit, flush, dispose };
}

/**
 * React wrapper around `createThrottledCommit`. Use for any control that emits
 * values continuously — most notably a native `<input type="color">` — so the
 * expensive downstream work can never queue up and stall the UI.
 */
export function useThrottledCommit<T>(
  commit: (value: T) => void,
  intervalMs = 100,
): { emit: (value: T) => void; flush: () => void } {
  const commitRef = useRef(commit);
  commitRef.current = commit;
  const throttledRef = useRef<ReturnType<typeof createThrottledCommit<T>> | null>(null);
  if (throttledRef.current === null) {
    throttledRef.current = createThrottledCommit<T>((value) => commitRef.current(value), intervalMs);
  }

  useEffect(() => () => throttledRef.current?.dispose(), []);

  const emit = useCallback((value: T) => throttledRef.current?.emit(value), []);
  const flush = useCallback(() => throttledRef.current?.flush(), []);
  return { emit, flush };
}
