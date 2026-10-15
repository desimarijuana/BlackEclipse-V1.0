// ── Aurora palette store ─────────────────────────────────────────────────────
// Client-side zustand store holding the user's Aurora customization (colors +
// motion + shape). Hydrated from localStorage after mount and written back on
// every change so the Settings panel and the live Aurora glow stay in sync (the
// Settings modal lives in a separate subtree from the Aurora, so a shared store
// beats prop drilling).
//
// The store keeps `palette`, `motion` and `shape` as separate fields for stable,
// granular selectors, but persists them as one `AuroraConfig` under the v2 key.

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
import {
  defaultAuroraConfig,
  defaultAuroraMotion,
  defaultAuroraShape,
  defaultAuroraStyle,
  loadAuroraConfig,
  normalizeAuroraMotion,
  normalizeAuroraShape,
  normalizeAuroraStyle,
  saveAuroraConfig,
  resetAuroraConfig,
  type AuroraMotion,
  type AuroraShape,
  type AuroraStyle,
} from './config';

export interface AuroraPaletteStore {
  palette: AuroraPalette;
  motion: AuroraMotion;
  shape: AuroraShape;
  style: AuroraStyle;
  hydrated: boolean;
  /** True while a non-persisted preset preview is showing. */
  previewing: boolean;
  /** Merge a hydrated config from localStorage (client only, post-mount). */
  hydrate: () => void;
  /** Set a single state's core or edge color. */
  setColor: (state: AuroraMarketState, key: keyof AuroraColorPair, value: string) => void;
  /** Replace the whole palette (preset application) and persist it. */
  setPalette: (palette: AuroraPalette) => void;
  /** Patch one or more motion knobs and persist. */
  setMotion: (patch: Partial<AuroraMotion>) => void;
  /** Patch one or more shape knobs and persist. */
  setShape: (patch: Partial<AuroraShape>) => void;
  /** Patch the render style and persist. */
  setStyle: (patch: Partial<AuroraStyle>) => void;
  /** Reset motion + shape + style to their shipped defaults (keeps colors). */
  resetLook: () => void;
  /** Show a palette WITHOUT persisting — theme-preset auditioning. */
  preview: (palette: AuroraPalette) => void;
  /** Discard an active preview, restoring the saved palette. */
  cancelPreview: () => void;
  reset: () => void;
}

/** Persist the four slices as one config object. */
function persistConfig(state: Pick<AuroraPaletteStore, 'palette' | 'motion' | 'shape' | 'style'>) {
  saveAuroraConfig({
    palette: state.palette,
    motion: state.motion,
    shape: state.shape,
    style: state.style,
  });
}

export const useAuroraPaletteStore = create<AuroraPaletteStore>((set) => ({
  // SSR-consistent defaults; the real config loads on mount (no hydration
  // mismatch, and the Aurora starts on the shipped identity).
  palette: defaultAuroraPalette(),
  motion: defaultAuroraMotion(),
  shape: defaultAuroraShape(),
  style: defaultAuroraStyle(),
  hydrated: false,
  previewing: false,

  hydrate: () => {
    const config = loadAuroraConfig();
    set({
      palette: config.palette,
      motion: config.motion,
      shape: config.shape,
      style: config.style,
      hydrated: true,
    });
  },

  setColor: (state, key, value) =>
    set((s) => {
      const palette: AuroraPalette = {
        ...s.palette,
        [state]: { ...s.palette[state], [key]: value },
      };
      // Keep writing the legacy v1 palette for backward-compatible readers.
      saveAuroraPalette(palette);
      persistConfig({ palette, motion: s.motion, shape: s.shape, style: s.style });
      return { palette };
    }),

  setPalette: (palette) => {
    // Normalize + clone so applying a preset never stores a shared module
    // reference (a later edit would otherwise mutate the preset itself).
    const clean = parseAuroraPalette(palette);
    set((s) => {
      saveAuroraPalette(clean);
      persistConfig({ palette: clean, motion: s.motion, shape: s.shape, style: s.style });
      return { palette: clean, previewing: false };
    });
  },

  setMotion: (patch) =>
    set((s) => {
      const motion = normalizeAuroraMotion({ ...s.motion, ...patch });
      persistConfig({ palette: s.palette, motion, shape: s.shape, style: s.style });
      return { motion };
    }),

  setShape: (patch) =>
    set((s) => {
      const shape = normalizeAuroraShape({ ...s.shape, ...patch });
      persistConfig({ palette: s.palette, motion: s.motion, shape, style: s.style });
      return { shape };
    }),

  setStyle: (patch) =>
    set((s) => {
      const style = normalizeAuroraStyle({ ...s.style, ...patch });
      persistConfig({ palette: s.palette, motion: s.motion, shape: s.shape, style });
      return { style };
    }),

  resetLook: () =>
    set((s) => {
      const motion = defaultAuroraMotion();
      const shape = defaultAuroraShape();
      const style = defaultAuroraStyle();
      persistConfig({ palette: s.palette, motion, shape, style });
      return { motion, shape, style };
    }),

  preview: (palette) => {
    const clean = parseAuroraPalette(palette);
    set({ palette: clean, previewing: true });
  },

  cancelPreview: () => {
    set({ palette: loadAuroraPalette(), previewing: false });
  },

  reset: () => {
    resetAuroraConfig();
    const clean = defaultAuroraConfig();
    set({
      palette: clean.palette,
      motion: clean.motion,
      shape: clean.shape,
      style: clean.style,
    });
  },
}));

/** Hydrate the Aurora customization from localStorage once, on the client. */
export function useHydrateAuroraPalette() {
  const hydrate = useAuroraPaletteStore((s) => s.hydrate);
  const hydrated = useAuroraPaletteStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
