"use client";

import { useEffect } from "react";
import { create } from "zustand";
import {
  normalizeChartColor,
  normalizeChartPalette,
  normalizeSection,
  type ChartPalette,
  type PaletteSection,
} from "./chart-palette";

interface ChartPaletteStore {
  palette: ReturnType<typeof normalizeChartPalette>;
  /**
   * Non-persisting overlay used by Settings › Customization's live theme
   * preview. When set, every consumer sees this instead of `palette`, so a
   * draft theme recolors charts and market heatmaps instantly. It is never
   * written to localStorage, and any explicit chart edit clears it.
   */
  previewPalette: ChartPalette | null;
  hydrated: boolean;
  storageAvailable: boolean;
  setPalette: (palette: unknown) => void;
  setSection: (section: PaletteSection, value: unknown) => void;
  setSeriesColor: (index: number, value: string) => void;
  reset: () => void;
  resetSection: (section: PaletteSection) => void;
  /** Show a non-persisted palette overlay (theme draft preview). */
  setPreview: (palette: unknown | null) => void;
  hydrate: () => void;
}

const STORAGE_KEY = "be_chart_palette_v2";
const SECTIONS: PaletteSection[] = ["candles", "lines", "heatmap"];
let listening = false;

function parseStoredPalette(value: string | null) {
  try {
    return normalizeChartPalette(value === null ? null : JSON.parse(value));
  } catch {
    return normalizeChartPalette(null);
  }
}

function persistPalette(palette: ReturnType<typeof normalizeChartPalette>): boolean {
  if (typeof window === "undefined") return false;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(palette));
    return true;
  } catch {
    return false;
  }
}

function listenToStorage() {
  if (listening || typeof window === "undefined") return;
  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY && event.key !== null) return;
    try {
      if (event.storageArea && event.storageArea !== window.localStorage) return;
    } catch {
      return;
    }
    useChartPaletteStore.setState({
      palette: parseStoredPalette(event.newValue),
      hydrated: true,
    });
  });
  listening = true;
}

export const useChartPaletteStore = create<ChartPaletteStore>((set, get) => ({
  palette: normalizeChartPalette(null),
  previewPalette: null,
  hydrated: false,
  storageAvailable: true,
  hydrate: () => {
    if (typeof window === "undefined") return;
    listenToStorage();
    if (get().hydrated) return;
    let palette = normalizeChartPalette(null);
    let storageAvailable = true;
    try {
      palette = parseStoredPalette(window.localStorage.getItem(STORAGE_KEY));
    } catch {
      storageAvailable = false;
    }
    set({ palette, hydrated: true, storageAvailable });
  },
  setPalette: (raw) => {
    get().hydrate();
    const palette = normalizeChartPalette(raw);
    const storageAvailable = persistPalette(palette);
    // An explicit edit ends any theme preview overlay so the user's own chart
    // choices are what they see.
    set({ palette, previewPalette: null, storageAvailable });
  },
  setPreview: (raw) => {
    const next = raw === null ? null : normalizeChartPalette(raw);
    const current = get().previewPalette;
    // Skip identical previews so rapid theme-drag ticks don't re-render every
    // chart consumer when the derived market colors did not actually change.
    if (JSON.stringify(next) === JSON.stringify(current)) return;
    set({ previewPalette: next });
  },
  setSection: (section, value) => {
    if (!SECTIONS.includes(section)) return;
    if (typeof value !== "object" || value === null || Array.isArray(value)) return;
    get().hydrate();
    get().setPalette({ ...get().palette, [section]: normalizeSection(section, value) });
  },
  setSeriesColor: (index, value) => {
    const color = normalizeChartColor(value);
    if (!color || !Number.isInteger(index) || index < 0 || index >= 6) return;
    get().hydrate();
    const series = [...get().palette.lines.series];
    series[index] = color;
    get().setPalette({ ...get().palette, lines: { ...get().palette.lines, series } });
  },
  reset: () => get().setPalette(null),
  resetSection: (section) => {
    if (!SECTIONS.includes(section)) return;
    get().hydrate();
    get().setPalette({ ...get().palette, [section]: normalizeSection(section, null) });
  },
}));

export function useChartPalette() {
  const palette = useChartPaletteStore((state) => state.previewPalette ?? state.palette);
  const hydrate = useChartPaletteStore((state) => state.hydrate);
  useEffect(() => hydrate(), [hydrate]);
  return palette;
}

/** The palette every consumer should render — the preview overlay if active. */
function effectivePalette(state: { palette: ChartPalette; previewPalette: ChartPalette | null }): ChartPalette {
  return state.previewPalette ?? state.palette;
}

export function getChartPalette() {
  useChartPaletteStore.getState().hydrate();
  return effectivePalette(useChartPaletteStore.getState());
}

export function subscribeChartPalette(listener: () => void): () => void {
  const unsubscribe = useChartPaletteStore.subscribe((state, previous) => {
    if (effectivePalette(state) !== effectivePalette(previous)) listener();
  });
  useChartPaletteStore.getState().hydrate();
  return unsubscribe;
}
