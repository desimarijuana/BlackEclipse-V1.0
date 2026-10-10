'use client';

// ── ChatBot conversation appearance (Settings › Customization › ChatBot Page) ─
// A small, self-contained preference for the conversation surface: the typeface
// used for user prompts, assistant replies and the composer. It is a single
// immediately-applied preference with its own store (like the app background),
// so the ChatBot tab can autosave without the theme draft/Apply model.
//
// The options reference the SAME self-hosted next/font display faces the landing
// wordmark uses (see `WORDMARK_FONT_OPTIONS` + `layout.tsx`), so every choice
// renders for real instead of silently falling back to a system font. An empty
// `font` follows the app's UI font (`--font-sans`), which is the default.
//
// Persistence: small prefs → localStorage (`be_chat_appearance_v1`). Applied as
// CSS custom properties (`--chat-font`) on <html>, which the chat components
// read via `var(--chat-font, var(--font-sans))`.

import { useEffect } from 'react';
import { create } from 'zustand';
import { WORDMARK_FONT_OPTIONS } from '@/lib/backgrounds';

export interface ChatAppearance {
  /** Font stack for the conversation. '' follows the app UI font. */
  font: string;
}

export const DEFAULT_CHAT_APPEARANCE: ChatAppearance = { font: '' };

export const CHAT_APPEARANCE_STORAGE_KEY = 'be_chat_appearance_v1';

/**
 * Fonts offered for the ChatBot conversation. "App font" (the default) follows
 * the theme's UI font; the rest are the self-hosted display faces, so a pick is
 * always a real, loaded typeface. Keep in sync with `WORDMARK_FONT_OPTIONS`.
 */
export const CHAT_FONT_OPTIONS: { label: string; value: string }[] = [
  { label: 'App font', value: '' },
  ...WORDMARK_FONT_OPTIONS,
];

export function normalizeChatAppearance(raw: unknown): ChatAppearance {
  const value = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
  const font = typeof value.font === 'string' && value.font.length <= 200
    ? value.font
    : DEFAULT_CHAT_APPEARANCE.font;
  return { font };
}

function load(): ChatAppearance {
  if (typeof window === 'undefined') return DEFAULT_CHAT_APPEARANCE;
  try {
    const raw = window.localStorage.getItem(CHAT_APPEARANCE_STORAGE_KEY);
    return raw ? normalizeChatAppearance(JSON.parse(raw)) : DEFAULT_CHAT_APPEARANCE;
  } catch {
    return DEFAULT_CHAT_APPEARANCE;
  }
}

function persist(appearance: ChatAppearance): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CHAT_APPEARANCE_STORAGE_KEY, JSON.stringify(appearance));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

/** Push the conversation font onto the document as a CSS variable. */
export function applyChatAppearanceToDocument(appearance: ChatAppearance): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (appearance.font) root.style.setProperty('--chat-font', appearance.font);
  else root.style.removeProperty('--chat-font');
}

export interface ChatAppearanceStore {
  appearance: ChatAppearance;
  hydrated: boolean;
  hydrate: () => void;
  /** Patch the appearance; applies immediately and persists. */
  setAppearance: (patch: Partial<ChatAppearance>) => void;
  /** Restore the shipped default (follow the app UI font). */
  reset: () => void;
}

export const useChatAppearanceStore = create<ChatAppearanceStore>((set, get) => ({
  appearance: DEFAULT_CHAT_APPEARANCE,
  hydrated: false,

  hydrate: () => {
    const appearance = load();
    applyChatAppearanceToDocument(appearance);
    set({ appearance, hydrated: true });
  },

  setAppearance: (patch) => {
    const next = normalizeChatAppearance({ ...get().appearance, ...patch });
    applyChatAppearanceToDocument(next);
    persist(next);
    set({ appearance: next });
  },

  reset: () => {
    applyChatAppearanceToDocument(DEFAULT_CHAT_APPEARANCE);
    persist(DEFAULT_CHAT_APPEARANCE);
    set({ appearance: DEFAULT_CHAT_APPEARANCE });
  },
}));

/** Hydrate the conversation appearance from storage and apply it, once. */
export function useHydrateChatAppearance() {
  const hydrate = useChatAppearanceStore((s) => s.hydrate);
  const hydrated = useChatAppearanceStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
