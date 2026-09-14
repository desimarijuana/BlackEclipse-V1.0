'use client';

// ── Market Workspace — chart link bus ────────────────────────────────────────
// Linked crosshair + range updates are HIGH FREQUENCY (every mouse move) and
// must NOT go through React state — doing so re-renders the whole workspace on
// every pixel of pointer movement (spec §9: one chart updating must not rerender
// every chart). Instead, linked charts talk through this module-level bus and
// apply updates imperatively on their chart provider.
//
// Symbol + timeframe links are low-frequency and go through the layout kernel.

export interface LinkRange {
  start: number;
  end: number;
}

type CrosshairListener = (time: number | null, sourcePanelId: string) => void;
type RangeListener = (range: LinkRange, sourcePanelId: string) => void;

class MarketLinkBus {
  private crosshairListeners = new Set<CrosshairListener>();
  private rangeListeners = new Set<RangeListener>();
  /** Latest values so a newly mounted linked chart can sync immediately. */
  private lastCrosshair: { time: number | null; source: string } | null = null;
  private lastRange: { range: LinkRange; source: string } | null = null;

  publishCrosshair(time: number | null, sourcePanelId: string): void {
    this.lastCrosshair = { time, source: sourcePanelId };
    for (const l of this.crosshairListeners) l(time, sourcePanelId);
  }

  publishRange(range: LinkRange, sourcePanelId: string): void {
    this.lastRange = { range, source: sourcePanelId };
    for (const l of this.rangeListeners) l(range, sourcePanelId);
  }

  subscribeCrosshair(cb: CrosshairListener): () => void {
    this.crosshairListeners.add(cb);
    if (this.lastCrosshair && this.lastCrosshair.source !== undefined) {
      cb(this.lastCrosshair.time, this.lastCrosshair.source);
    }
    return () => { this.crosshairListeners.delete(cb); };
  }

  subscribeRange(cb: RangeListener): () => void {
    this.rangeListeners.add(cb);
    if (this.lastRange) cb(this.lastRange.range, this.lastRange.source);
    return () => { this.rangeListeners.delete(cb); };
  }
}

/** Singleton link bus — shared by every chart panel. */
export const linkBus = new MarketLinkBus();

/** Convenience: link a whole group of chart panels (all peers, any link on). */
export function linkGroupHas(list: Array<{ link?: { crosshair?: boolean; range?: boolean } }>, key: 'crosshair' | 'range'): boolean {
  return list.some(p => p.link?.[key]);
}
