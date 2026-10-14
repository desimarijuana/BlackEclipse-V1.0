'use client';

import React, { useState, useEffect } from 'react';
import { fetchWithRetry, logHandledFetchFailure } from '@/lib/fetch-retry';

// ── Global Markets overview ──────────────────────────────────────────────────
// Extracted from market-overview.tsx (memory/simplicity standing goal): this
// module owns the /api/global-overview fetch, the persisted GmConfig
// preferences, and the pointer-based drag-reorder engine. The screen keeps
// only the JSX that renders what this hook returns.

export type GmLayout = 'compact' | 'comfortable' | 'focus';
export type GmColumns = { ticker: boolean; name: boolean; price: boolean; change: boolean; cap: boolean };
export type GmColumnKey = keyof GmColumns;
export type GmConfig = {
  layout: GmLayout;
  columns: GmColumns;
  columnOrder: GmColumnKey[]; // left → right display order of table columns
  rows: number;
  countries: string[] | null;
  sortBy: 'cap' | 'change' | 'price' | 'name';
  movers: 'all' | 'gainers' | 'losers';
  dense: boolean;
  showRank: boolean;
  highlightExtremes: boolean;
  groupOrder: 'az' | 'movers';
  order: string[] | null; // manual country-card order (drag & drop / buttons)
};

export type OverviewStock = {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
  marketCap?: number | null;
};

export type OverviewGroup = {
  id: string;
  country: string;
  name?: string;
  exchange: string;
  isCrypto: boolean;
  currency: string;
  indexName?: string;
  index?: { symbol: string; name: string; price: number; changePct: number } | null;
  stocks: OverviewStock[];
};

export const GM_CONFIG_KEY = 'be_gm_config';
export const GM_COLUMN_ORDER: GmColumnKey[] = ['ticker', 'name', 'price', 'cap', 'change'];
export const GM_COLUMN_LABELS: Record<GmColumnKey, string> = {
  ticker: 'Ticker', name: 'Name', price: 'Price', cap: 'Mkt Cap', change: 'Change %',
};
export const GM_DEFAULTS: GmConfig = {
  layout: 'compact',
  columns: { ticker: true, name: true, price: true, change: true, cap: true },
  columnOrder: GM_COLUMN_ORDER,
  rows: 5,
  countries: null, // null = all countries
  sortBy: 'cap',
  movers: 'all',
  dense: false,
  showRank: false,
  highlightExtremes: false,
  groupOrder: 'az',
  order: null,
};

/** Generic list reorder used by the ordering buttons in the config panel. */
export function reorderList<T>(list: T[], item: T, dir: -1 | 1): T[] {
  const i = list.indexOf(item);
  const j = i + dir;
  if (i === -1 || j < 0 || j >= list.length) return list;
  const next = [...list];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

export function useGlobalMarkets(active: boolean) {
  const [globalOverview, setGlobalOverview] = useState<OverviewGroup[]>([]);
  const [loadingGlobalMarkets, setLoadingGlobalMarkets] = useState(false);
  // Visually marks the clicked row so selection stays obvious across cards.
  const [gmSelectedRow, setGmSelectedRow] = useState<{ marketId: string; symbol: string } | null>(null);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    (async () => {
      setLoadingGlobalMarkets(true);
      try {
        const res = await fetchWithRetry('/api/global-overview');
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.groups)) {
          setGlobalOverview(data.groups);
        }
      } catch (err) {
        logHandledFetchFailure('Failed to load global overview:', err);
      } finally {
        if (!cancelled) setLoadingGlobalMarkets(false);
      }
    })();
    return () => { cancelled = true; };
  }, [active]);

  const [gmConfig, setGmConfig] = useState<GmConfig>(GM_DEFAULTS);
  const [gmConfigOpen, setGmConfigOpen] = useState(false);
  // Free-text filter for the markets tab (matches market name/id/exchange/
  // country). Previously the search box was wired to the stock search state,
  // which nothing on this tab read — typing filtered nothing.
  const [gmSearch, setGmSearch] = useState('');
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(GM_CONFIG_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setGmConfig((prev) => ({
          ...prev,
          ...parsed,
          columns: { ...prev.columns, ...(parsed.columns || {}) },
          columnOrder: Array.isArray(parsed.columnOrder)
            // Repair saved orders missing/duplicating keys after app updates.
            ? GM_COLUMN_ORDER.filter((k) => parsed.columnOrder.includes(k))
              .concat(GM_COLUMN_ORDER.filter((k) => !parsed.columnOrder.includes(k)))
            : prev.columnOrder,
        }));
      }
    } catch { /* ignore corrupted storage */ }
  }, []);
  const applyGmConfig = (patch: Partial<GmConfig>) => {
    setGmConfig((prev) => {
      const next = { ...prev, ...patch };
      try { window.localStorage.setItem(GM_CONFIG_KEY, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  };
  // Move a column left/right in the display order.
  const moveGmColumn = (key: GmColumnKey, dir: -1 | 1) => {
    const order = [...(gmConfig.columnOrder ?? GM_COLUMN_ORDER)];
    const i = order.indexOf(key);
    const j = i + dir;
    if (i === -1 || j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    applyGmConfig({ columnOrder: order });
  };

  // Drag & drop reordering of the market tables — custom pointer-based drag.
  // 100% DOM-driven while dragging: the floating copy follows the cursor via
  // direct transforms, and the preview reorder moves real DOM nodes with FLIP
  // animations. ZERO React re-renders during the drag (state only changes on
  // drag start/end), which is what keeps it buttery smooth.
  const [gmDragId, setGmDragId] = useState<string | null>(null);
  const [gmDragWidth, setGmDragWidth] = useState(0);
  const gmFloatRef = React.useRef<HTMLDivElement | null>(null);
  const gmLastTargetRef = React.useRef<string | null>(null);
  const gmScrollerRef = React.useRef<HTMLElement | null>(null);
  const gmScrollTopRef = React.useRef(0);
  const gmScrollSpeedRef = React.useRef(0);
  const gmScrollRAF = React.useRef<number | null>(null);

  // Commit the CURRENT on-screen DOM order as the saved preference. The live
  // preview already moved the dragged card to exactly where the user dropped
  // it — persisting what they see is always correct, in every direction.
  const commitGmDomOrder = (grid: HTMLElement) => {
    const order: string[] = [];
    grid.querySelectorAll<HTMLElement>('[data-gm-card]').forEach((el) => {
      const gid = el.getAttribute('data-gm-id');
      if (gid) order.push(gid);
    });
    if (order.length > 0) applyGmConfig({ order });
  };

  // DOM-level preview reorder: move the (hidden) dragged card's node to the
  // target's slot, then FLIP-animate every other card from its old position.
  // No React state involved — the grid re-renders only on drop.
  const domPreviewReorder = (grid: HTMLElement, draggedId: string, targetId: string) => {
    const cards = [...grid.querySelectorAll<HTMLElement>('[data-gm-card]')];
    const draggedEl = cards.find(el => el.getAttribute('data-gm-id') === draggedId);
    const targetEl = cards.find(el => el.getAttribute('data-gm-id') === targetId);
    if (!draggedEl || !targetEl || draggedEl === targetEl) return;
    const from = cards.indexOf(draggedEl);
    const to = cards.indexOf(targetEl);
    if (to === from) return;

    // Record old centers for FLIP.
    const old = new Map<string, { x: number; y: number }>();
    cards.forEach(el => {
      const r = el.getBoundingClientRect();
      old.set(el.getAttribute('data-gm-id')!, { x: r.left + r.width / 2, y: r.top + r.height / 2 });
    });

    // Move the dragged node to the target's slot.
    if (to > from) {
      grid.insertBefore(draggedEl, cards[to + 1] ?? null);
    } else {
      grid.insertBefore(draggedEl, cards[to]);
    }

    // FLIP every other card from its old center to its new one.
    grid.querySelectorAll<HTMLElement>('[data-gm-card]').forEach(el => {
      if (el === draggedEl) return;
      const gid = el.getAttribute('data-gm-id');
      if (!gid) return;
      const f = old.get(gid);
      if (!f) return;
      const r = el.getBoundingClientRect();
      const dx = f.x - (r.left + r.width / 2);
      const dy = f.y - (r.top + r.height / 2);
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      el.style.transition = 'none';
      el.style.transform = `translate(${dx}px, ${dy}px)`;
      requestAnimationFrame(() => {
        el.style.transition = 'transform 300ms cubic-bezier(.22,.9,.24,1)';
        el.style.transform = '';
      });
    });
  };

  const beginGmDrag = (clientX: number, clientY: number, button: number, anchor: HTMLElement) => {
    if (button !== 0) return;
    const card = anchor.closest('[data-gm-card]') as HTMLElement | null;
    if (!card) return;
    const grid = card.parentElement;
    if (!grid) return;
    const id = card.getAttribute('data-gm-id');
    if (!id) return;

    // The scroll container (the page's main scroller) for edge auto-scroll.
    // Must actually be scrollable — an overflow-y:auto ancestor with no
    // overflow (scrollHeight === clientHeight) is not the real scroller.
    const scroller = (() => {
      let el: HTMLElement | null = card;
      while (el) {
        const s = getComputedStyle(el);
        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1) {
          return el;
        }
        el = el.parentElement;
      }
      return document.scrollingElement as HTMLElement | null;
    })();
    gmScrollerRef.current = scroller;
    gmScrollTopRef.current = scroller?.scrollTop ?? 0;

    const startX = clientX;
    const startY = clientY;
    const cardRect = card.getBoundingClientRect();
    let started = false;

    // LIVE hit-test against the current on-screen card rects (NOT a drag-start
    // snapshot — cards FLIP to new slots as the preview reorders, so stale
    // rects made placing into center/other rows fail). Padding covers the
    // small grid gaps so dropping between cards also works.
    const liveHitTest = (x: number, y: number): string | null => {
      const PAD = 8;
      let best: string | null = null;
      let bestDist = Infinity;
      const cards = grid.querySelectorAll<HTMLElement>('[data-gm-card]');
      for (const el of cards) {
        const gid = el.getAttribute('data-gm-id');
        if (!gid || gid === id) continue;
        const r = el.getBoundingClientRect();
        if (x < r.left - PAD || x > r.right + PAD || y < r.top - PAD || y > r.bottom + PAD) continue;
        const d = Math.hypot(x - (r.left + r.width / 2), y - (r.top + r.height / 2));
        if (d < bestDist) {
          bestDist = d;
          best = gid;
        }
      }
      return best;
    };

    // Edge auto-scroll: near the top/bottom of the viewport, scroll the
    // container so the user can reach tables above/below the fold.
    const EDGE = 90;
    const MAX_SPEED = 18;
    const scrollStep = () => {
      if (!started) return;
      const speed = gmScrollSpeedRef.current;
      if (speed === 0 || !scroller) return;
      scroller.scrollTop += speed;
      gmScrollTopRef.current = scroller.scrollTop;
      gmScrollRAF.current = requestAnimationFrame(scrollStep);
    };
    const updateAutoScroll = (y: number) => {
      const vh = window.innerHeight;
      let speed = 0;
      if (y < EDGE) speed = -Math.min(MAX_SPEED, ((EDGE - y) / EDGE) * MAX_SPEED);
      else if (y > vh - EDGE) speed = Math.min(MAX_SPEED, ((y - (vh - EDGE)) / EDGE) * MAX_SPEED);
      gmScrollSpeedRef.current = speed;
      if (speed !== 0 && gmScrollRAF.current === null) {
        gmScrollRAF.current = requestAnimationFrame(scrollStep);
      }
    };

    const onMove = (ev: MouseEvent) => {
      if (!started) {
        if (Math.abs(ev.clientX - startX) < 5 && Math.abs(ev.clientY - startY) < 5) return;
        started = true;
        setGmDragId(id);
        setGmDragWidth(cardRect.width);
        document.body.style.userSelect = 'none';
      }
      // The floating copy follows the cursor via direct DOM transform (no
      // state → no re-render → no lag). Centered on the pointer (-50%,-50%)
      // so it stays glued to the mouse arrow wherever it moves.
      const floatEl = gmFloatRef.current;
      if (floatEl) {
        floatEl.style.transform = `translate3d(${ev.clientX}px, ${ev.clientY}px, 0) translate(-50%, -50%) scale(1.02)`;
      }
      // Live preview: move the real DOM node + FLIP the others. Pure DOM work,
      // zero React renders — this is what keeps the drag smooth.
      const target = liveHitTest(ev.clientX, ev.clientY);
      if (target && gmLastTargetRef.current !== target) {
        gmLastTargetRef.current = target;
        domPreviewReorder(grid, id, target);
      }
      updateAutoScroll(ev.clientY);
    };
    const cleanup = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      if (gmScrollRAF.current !== null) {
        cancelAnimationFrame(gmScrollRAF.current);
        gmScrollRAF.current = null;
      }
      gmScrollSpeedRef.current = 0;
      gmLastTargetRef.current = null;
      gmScrollerRef.current = null;
      setGmDragId(null);
    };
    const onUp = () => {
      // The preview moved the (invisible) dragged card into its final slot.
      // Commit the on-screen DOM order — exactly what the user sees.
      cleanup();
      if (!started) return;
      commitGmDomOrder(grid);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  return {
    globalOverview,
    loadingGlobalMarkets,
    gmSelectedRow,
    setGmSelectedRow,
    gmConfig,
    gmConfigOpen,
    setGmConfigOpen,
    gmSearch,
    setGmSearch,
    applyGmConfig,
    moveGmColumn,
    gmDragId,
    gmDragWidth,
    gmFloatRef,
    beginGmDrag,
  };
}
