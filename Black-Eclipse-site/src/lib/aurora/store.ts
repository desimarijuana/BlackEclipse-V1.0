// ── Aurora palette store ─────────────────────────────────────────────────────
// Client-side zustand store holding the user's Aurora colors. Hydrated from
// localStorage after mount and written back on every change so the Settings
// panel and the live Aurora glow stay in sync (the Settings modal lives in a
// separate subtree from the Aurora, so a shared store beats prop drilling).

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import {
  defaultAuroraPalette,
  loadAuroraPalette,
  parseAuroraPalette,
  resetAuroraPalette,
  saveAuroraPalette,
  type AuroraColorPair,
  type AuroraMarketState,
  type AuroraPalette,
} from './theme';

export interface AuroraPaletteStore {
  palette: AuroraPalette;
  hydrated: boolean;
  /** True while a non-persisted preset preview is showing. */
  previewing: boolean;
  /** Merge a hydrated palette from localStorage (client only, post-mount). */
  hydrate: () => void;
  /** Set a single state's core or edge color. */
  setColor: (state: AuroraMarketState, key: keyof AuroraColorPair, value: string) => void;
  /** Replace the whole palette (preset application) and persist it. */
  setPalette: (palette: AuroraPalette) => void;
  /** Show a palette WITHOUT persisting — theme-preset auditioning. */
  preview: (palette: AuroraPalette) => void;
  /** Discard an active preview, restoring the saved palette. */
  cancelPreview: () => void;
  reset: () => void;
}

export const useAuroraPaletteStore = create<AuroraPaletteStore>((set) => ({
  // SSR-consistent default; the real palette loads on mount (no hydration
  // mismatch, and the Aurora starts on the shipped identity).
  palette: defaultAuroraPalette(),
  hydrated: false,
  previewing: false,

  hydrate: () => {
    const palette = loadAuroraPalette();
    set({ palette, hydrated: true });
  },

  setColor: (state, key, value) =>
    set((s) => {
      const palette: AuroraPalette = {
        ...s.palette,
        [state]: { ...s.palette[state], [key]: value },
      };
      saveAuroraPalette(palette);
      return { palette };
    }),

  setPalette: (palette) => {
    // Normalize + clone so applying a preset never stores a shared module
    // reference (a later edit would otherwise mutate the preset itself).
    const clean = parseAuroraPalette(palette);
    saveAuroraPalette(clean);
    set({ palette: clean, previewing: false });
  },

  preview: (palette) => {
    const clean = parseAuroraPalette(palette);
    set({ palette: clean, previewing: true });
  },

  cancelPreview: () => {
    set({ palette: loadAuroraPalette(), previewing: false });
  },

  reset: () => {
    resetAuroraPalette();
    set({ palette: defaultAuroraPalette() });
  },
}));

/** Hydrate the Aurora palette from localStorage once, on the client. */
export function useHydrateAuroraPalette() {
  const hydrate = useAuroraPaletteStore((s) => s.hydrate);
  const hydrated = useAuroraPaletteStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
