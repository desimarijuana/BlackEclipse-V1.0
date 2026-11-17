// ── Selected-text highlight bands ────────────────────────────────────────────
//
// The browser paints a selection only over the glyph boxes. With the chat's
// relaxed line-height and `space-y` block rhythm that leaves visible stripes
// between lines and paragraphs, so a selection reads as broken. We keep the
// native highlight (crisp glyphs) and paint the empty bands BETWEEN its client
// rects with the same accent. `selectionGapFillers` is pure so the geometry is
// testable without a DOM.

/** The subset of `DOMRect` this geometry needs. */
export interface RectLike {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export type Band = RectLike;

export interface Filler {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Rects whose tops differ by less than this are the same rendered line. */
const LINE_TOLERANCE_PX = 2;
/** Do not bridge a gap taller than this — a large jump is not a line gap. */
const MAX_GAP_PX = 26;
/** A guard against pathological ranges (huge tables, select-all). */
const MAX_FILLERS = 240;

function isUsable(rect: RectLike): boolean {
  return (
    Number.isFinite(rect.left) &&
    Number.isFinite(rect.top) &&
    Number.isFinite(rect.right) &&
    Number.isFinite(rect.bottom) &&
    rect.right - rect.left > 0.5 &&
    rect.bottom - rect.top > 0.5
  );
}

/**
 * Collapse per-text-node client rects into one band per rendered line. A line
 * can produce several rects (one per inline node); the band spans them all.
 */
export function selectionBands(rects: readonly RectLike[]): Band[] {
  const usable = rects.filter(isUsable).sort((a, b) => a.top - b.top || a.left - b.left);
  const bands: Band[] = [];

  for (const rect of usable) {
    const band = bands[bands.length - 1];
    if (band && Math.abs(rect.top - band.top) <= LINE_TOLERANCE_PX) {
      band.left = Math.min(band.left, rect.left);
      band.top = Math.min(band.top, rect.top);
      band.right = Math.max(band.right, rect.right);
      band.bottom = Math.max(band.bottom, rect.bottom);
      continue;
    }
    bands.push({ left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom });
  }

  return bands;
}

/**
 * The empty vertical bands between consecutive selected lines. A filler is only
 * emitted when the two lines overlap horizontally, so a selection that jumps
 * across a column break never paints unrelated space.
 */
export function selectionGapFillers(rects: readonly RectLike[]): Filler[] {
  const bands = selectionBands(rects);
  const fillers: Filler[] = [];

  for (let i = 1; i < bands.length && fillers.length < MAX_FILLERS; i += 1) {
    const prev = bands[i - 1];
    const next = bands[i];
    const gap = next.top - prev.bottom;
    if (gap <= 0.5 || gap > MAX_GAP_PX) continue;

    const left = Math.max(prev.left, next.left);
    const right = Math.min(prev.right, next.right);
    if (right - left <= 1) continue;

    fillers.push({ left, top: prev.bottom, width: right - left, height: gap });
  }

  return fillers;
}
