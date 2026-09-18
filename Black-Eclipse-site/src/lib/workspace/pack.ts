// ── Masonry packing (pure) ───────────────────────────────────────────────────
// The track board treats a section's COLUMNS as vertical tracks and rebalances
// that section's widget cards into the shortest track. That is what removes
// vertical dead space: a short card can no longer be stranded beside a tall one
// — the next card simply flows underneath it, and every track in a section ends
// at roughly the same bottom edge.
//
// Rebalancing mutates the tree (column membership + order) rather than being a
// render-time projection, so the persisted layout, the drag/drop indices and
// the rendered result all agree. The estimator is measurement-free: pinned
// height → resolved min-height → a nominal unit.

import type { WorkspaceColumn, WorkspaceLayout, WidgetPlacement, WorkspaceZone } from './types';

/** Nominal height for a card with neither a pinned nor a minimum height. */
export const DEFAULT_CARD_ESTIMATE = 280;

export interface PackOptions {
  /**
   * Resolve a card's estimated height. Defaults to pinned height → resolved
   * min-height → DEFAULT_CARD_ESTIMATE (in that order).
   */
  heightOf?: (placement: WidgetPlacement) => number;
}

export function defaultHeightOf(placement: WidgetPlacement): number {
  if (typeof placement.height === 'number') return placement.height;
  if (typeof placement.defaultHeight === 'number') return placement.defaultHeight;
  if (typeof placement.minHeight === 'number') return placement.minHeight;
  return DEFAULT_CARD_ESTIMATE;
}

/** Index of the shortest track, ties broken leftmost. */
function shortestTrackIndex(heights: number[]): number {
  let best = 0;
  for (let i = 1; i < heights.length; i++) {
    if (heights[i] < heights[best]) best = i;
  }
  return best;
}

/**
 * Rebalance ONE section's cards across its columns by estimated height. Column
 * identity, count and weights are preserved; only `widgets` membership changes.
 * Cards keep their relative document order per track. A single-column section is
 * a no-op.
 */
export function rebalanceColumns(columns: WorkspaceColumn[], opts: PackOptions = {}): void {
  if (columns.length < 2) return;
  const heightOf = opts.heightOf ?? defaultHeightOf;

  // Document order across the section's columns.
  const ordered: WidgetPlacement[] = [];
  for (const col of columns) ordered.push(...col.widgets);

  const buckets: WidgetPlacement[][] = columns.map(() => []);
  const heights = new Array<number>(columns.length).fill(0);
  for (const placement of ordered) {
    const idx = shortestTrackIndex(heights);
    buckets[idx].push(placement);
    heights[idx] += heightOf(placement);
  }
  columns.forEach((col, i) => { col.widgets = buckets[i]; });
}

/**
 * Rebalance every multi-column section of a layout. Idempotent for a layout
 * already packed with the same estimator (the estimates are stable, so the
 * shortest-track assignment reproduces itself).
 */
export function rebalanceLayout(layout: WorkspaceLayout, opts: PackOptions = {}): void {
  for (const section of layout.sections) rebalanceColumns(section.columns, opts);
}

/** Estimated total height of each column (used to verify even packing). */
export function columnHeights(columns: WorkspaceColumn[], opts: PackOptions = {}): number[] {
  const heightOf = opts.heightOf ?? defaultHeightOf;
  return columns.map(c => c.widgets.reduce((a, w) => a + heightOf(w), 0));
}

/** Zone of a card — kept for callers that need to reason about placement. */
export function zoneOf(layout: WorkspaceLayout, placementId: string): WorkspaceZone | null {
  for (const section of layout.sections) {
    for (const column of section.columns) {
      if (column.widgets.some(w => w.id === placementId)) return section.zone ?? 'main';
    }
  }
  return null;
}
