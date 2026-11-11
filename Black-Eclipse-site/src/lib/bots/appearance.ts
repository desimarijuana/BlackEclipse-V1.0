'use client';

// ── Bots workspace appearance (text size) ────────────────────────────────────
// A small, self-contained preference for the Bots surfaces: the conversation,
// the bot list / group list in the sidebar, and the bot details drawer. It is
// deliberately separate from the app-wide theme `fontScale` so an operator can
// enlarge bot transcripts without inflating every other screen.
//
// Persistence: localStorage (`be_bots_appearance_v1`). Applied as the CSS
// custom property `--bots-font-scale` on <html>; `bots-text-scope` in
// globals.css multiplies the fixed sizes the bot components use by it.

import { useEffect } from 'react';
import { create } from 'zustand';

export interface BotsAppearance {
  /** Multiplier applied to bot-side text. 1 = the shipped sizes. */
  fontScale: number;
}

export const DEFAULT_BOTS_APPEARANCE: BotsAppearance = { fontScale: 1 };

export const BOTS_APPEARANCE_STORAGE_KEY = 'be_bots_appearance_v1';

export const BOTS_FONT_SCALE_MIN = 0.9;
export const BOTS_FONT_SCALE_MAX = 1.6;

/** Named steps, small enough to fit a dropdown. Values are multipliers. */
export const BOTS_FONT_SCALE_OPTIONS = [
  { label: 'Smaller', value: 0.9 },
  { label: 'Default', value: 1 },
  { label: 'Large', value: 1.15 },
  { label: 'Larger', value: 1.3 },
  { label: 'Largest', value: 1.5 },
] as const;

function clampFontScale(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_BOTS_APPEARANCE.fontScale;
  return Math.min(BOTS_FONT_SCALE_MAX, Math.max(BOTS_FONT_SCALE_MIN, value));
}

export function normalizeBotsAppearance(raw: unknown): BotsAppearance {
  const value = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
  const fontScale = typeof value.fontScale === 'number'
    ? clampFontScale(value.fontScale)
    : DEFAULT_BOTS_APPEARANCE.fontScale;
  return { fontScale };
}

function load(): BotsAppearance {
  if (typeof window === 'undefined') return DEFAULT_BOTS_APPEARANCE;
  try {
    const raw = window.localStorage.getItem(BOTS_APPEARANCE_STORAGE_KEY);
    return raw ? normalizeBotsAppearance(JSON.parse(raw)) : DEFAULT_BOTS_APPEARANCE;
  } catch {
    return DEFAULT_BOTS_APPEARANCE;
  }
}

function persist(appearance: BotsAppearance): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(BOTS_APPEARANCE_STORAGE_KEY, JSON.stringify(appearance));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

/** Push the bot text scale onto the document as a CSS variable. */
export function applyBotsAppearanceToDocument(appearance: BotsAppearance): void {
  if (typeof document === 'undefined') return;
  document.documentElement.style.setProperty('--bots-font-scale', String(appearance.fontScale));
}

export interface BotsAppearanceStore {
  appearance: BotsAppearance;
  hydrated: boolean;
  hydrate: () => void;
  /** Set the bot text multiplier; applies immediately and persists. */
  setFontScale: (value: number) => void;
  /** Restore the shipped default (100%). */
  reset: () => void;
}

export const useBotsAppearanceStore = create<BotsAppearanceStore>((set, get) => ({
  appearance: DEFAULT_BOTS_APPEARANCE,
  hydrated: false,

  hydrate: () => {
    const appearance = load();
    applyBotsAppearanceToDocument(appearance);
    set({ appearance, hydrated: true });
  },

  setFontScale: (value) => {
    const next = normalizeBotsAppearance({ ...get().appearance, fontScale: value });
    applyBotsAppearanceToDocument(next);
    persist(next);
    set({ appearance: next });
  },

  reset: () => {
    applyBotsAppearanceToDocument(DEFAULT_BOTS_APPEARANCE);
    persist(DEFAULT_BOTS_APPEARANCE);
    set({ appearance: DEFAULT_BOTS_APPEARANCE });
  },
}));

/** Hydrate the bot text size from storage and apply it, once. */
export function useHydrateBotsAppearance() {
  const hydrate = useBotsAppearanceStore((s) => s.hydrate);
  const hydrated = useBotsAppearanceStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
