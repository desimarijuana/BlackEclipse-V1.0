// ── Ghost gaze hook ──────────────────────────────────────────────────────────
// Shared cursor tracking for live bot faces. One window `pointermove` listener
// is bound for the whole page (ref-counted) and fans out to every subscribed
// avatar, so N animated faces cost one listener, not N. Each subscriber writes
// normalized `--look-x` / `--look-y` custom properties onto its own element;
// the SVG reads them in CSS. No React re-render per move — the browser paints.

'use client';

import { useEffect, type RefObject } from 'react';

type GazeListener = (clientX: number, clientY: number) => void;

const listeners = new Set<GazeListener>();
let bound = false;
let raf = 0;
let lastX = 0;
let lastY = 0;

function flush(): void {
  raf = 0;
  for (const fn of listeners) fn(lastX, lastY);
}

function onPointerMove(event: PointerEvent): void {
  lastX = event.clientX;
  lastY = event.clientY;
  if (!raf) raf = requestAnimationFrame(flush);
}

function bind(): void {
  if (bound || typeof window === 'undefined') return;
  bound = true;
  window.addEventListener('pointermove', onPointerMove, { passive: true });
}

function unbind(): void {
  if (!bound) return;
  bound = false;
  window.removeEventListener('pointermove', onPointerMove);
  if (raf) cancelAnimationFrame(raf);
  raf = 0;
}

function clampUnit(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(-1, Math.min(1, value));
}

/**
 * Make `ref`'s element look toward the cursor. Does nothing until `enabled` is
 * true; each subscriber is removed (and the shared listener unbound once the
 * last one leaves) on unmount.
 */
export function useGhostGaze(
  ref: RefObject<HTMLElement | null>,
  enabled: boolean,
): void {
  useEffect(() => {
    const el = ref.current;
    if (!enabled || !el) return;

    const listener: GazeListener = (clientX, clientY) => {
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const x = (clientX - (rect.left + rect.width / 2)) / (rect.width / 2);
      const y = (clientY - (rect.top + rect.height / 2)) / (rect.height / 2);
      el.style.setProperty('--look-x', String(clampUnit(x)));
      el.style.setProperty('--look-y', String(clampUnit(y)));
    };

    listeners.add(listener);
    bind();
    return () => {
      listeners.delete(listener);
      if (listeners.size === 0) unbind();
    };
  }, [ref, enabled]);
}
