'use client';

// ── Forward wheel scroll to a target ─────────────────────────────────────────
// The ChatBot transcript is the only vertical scroll area, but the composer and
// toolbar are DOM siblings of it, so the browser's native wheel chaining never
// reaches the transcript and a mouse wheel / trackpad over those areas did
// nothing ("scroll is broken"). This handler forwards the delta onto the
// transcript, while leaving any nested vertical scrollable (a multi-line
// composer, an open palette) to scroll itself.

import { useCallback } from 'react';

export function useForwardWheelScroll(scrollRef: React.RefObject<HTMLDivElement | null>) {
  return useCallback(
    (e: React.WheelEvent<HTMLDivElement>) => {
      const el = scrollRef.current;
      if (!el) return;
      let node = e.target as HTMLElement | null;
      while (node && node !== e.currentTarget) {
        const style = window.getComputedStyle(node);
        if (
          (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
          node.scrollHeight > node.clientHeight + 1
        ) {
          return;
        }
        node = node.parentElement;
      }
      const before = el.scrollTop;
      el.scrollTop = before + e.deltaY;
      if (el.scrollTop !== before) e.preventDefault();
    },
    [scrollRef],
  );
}
