'use client';

// ── Forward wheel / trackpad scroll to a target scroll area ──────────────────
// The app shell is a fixed-height frame (`body { overflow: hidden }`) whose only
// vertical scroll area on the ChatBot page is the transcript. The header, the
// composer and the padding around the transcript are DOM siblings of it, so the
// browser's native wheel chaining never reaches the transcript: resting a mouse
// wheel or, especially, a laptop trackpad over that chrome did nothing.
//
// This installs ONE native, NON-PASSIVE wheel listener on the document and
// forwards the delta onto the transcript — unless the pointer is over something
// that genuinely scrolls itself (the transcript, a multi-line composer, a code
// block, an open palette, the sidebar list), in which case that element is left
// to handle its own scrolling.
//
// Two things the previous React `onWheel` version got wrong, both fixed here:
//   * React registers `onWheel` as a PASSIVE listener, so `preventDefault()`
//     threw "Unable to preventDefault inside passive event listener invocation"
//     and could not stop the (non-existent) default chaining. A native
//     `{ passive: false }` listener can.
//   * `deltaY` was applied raw. Trackpads (and Firefox) can report
//     `deltaMode === DOM_DELTA_LINE` (1) or `DOM_DELTA_PAGE` (2), where a delta
//     of `3` means three LINES, not three pixels — applying it verbatim moved
//     the transcript a few pixels per event and read as "scroll is broken".
//     Deltas are normalised to pixels below.

import { useEffect, type RefObject } from 'react';

/** Assumed px per line for `DOM_DELTA_LINE` wheel events. */
const LINE_HEIGHT = 16;

export function useForwardWheelScroll(
  targetRef: RefObject<HTMLDivElement | null>,
  enabled = true,
): void {
  useEffect(() => {
    if (!enabled) return;

    const onWheel = (e: WheelEvent) => {
      // Browser zoom (pinch / ctrl+wheel) and anything that already handled the
      // event (a chart zoom, the 3D orbit control) must be left alone.
      if (e.ctrlKey || e.defaultPrevented) return;

      const target = targetRef.current;
      if (!target) return;

      // Walk up from the event target: if something under the pointer is
      // itself a non-empty vertical scroller, let it scroll instead.
      let node = e.target as HTMLElement | null;
      while (node && node !== document.body) {
        const style = window.getComputedStyle(node);
        if (
          (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
          node.scrollHeight > node.clientHeight + 1
        ) {
          return;
        }
        node = node.parentElement;
      }

      const unit =
        e.deltaMode === 1 ? LINE_HEIGHT : e.deltaMode === 2 ? target.clientHeight : 1;
      const delta = e.deltaY * unit;
      if (delta === 0) return;

      const before = target.scrollTop;
      target.scrollTop = before + delta;
      if (target.scrollTop !== before) e.preventDefault();
    };

    document.addEventListener('wheel', onWheel, { passive: false });
    return () => document.removeEventListener('wheel', onWheel);
  }, [targetRef, enabled]);
}
