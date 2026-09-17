"use client";

import { useEffect } from "react";
import { create } from "zustand";
import {
  normalizeChartColor,
  normalizeChartPalette,
  normalizeSection,
  type PaletteSection,
} from "./chart-palette";

interface ChartPaletteStore {
  palette: ReturnType<typeof normalizeChartPalette>;
  hydrated: boolean;
  storageAvailable: boolean;
  setPalette: (palette: unknown) => void;
  setSection: (section: PaletteSection, value: unknown) => void;
  setSeriesColor: (index: number, value: string) => void;
  reset: () => void;
  resetSection: (section: PaletteSection) => void;
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
    set({ palette, storageAvailable });
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
  const palette = useChartPaletteStore((state) => state.palette);
  const hydrate = useChartPaletteStore((state) => state.hydrate);
  useEffect(() => hydrate(), [hydrate]);
  return palette;
}

export function getChartPalette() {
  useChartPaletteStore.getState().hydrate();
  return useChartPaletteStore.getState().palette;
}

export function subscribeChartPalette(listener: () => void): () => void {
  const unsubscribe = useChartPaletteStore.subscribe((state, previous) => {
    if (state.palette !== previous.palette) listener();
  });
  useChartPaletteStore.getState().hydrate();
  return unsubscribe;
}
