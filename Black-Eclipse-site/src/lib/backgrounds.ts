// ── App background (Settings › General › Background) ────────────────────────
// One place for the app's backdrop: the old pattern treatment (flat / gradient
// / grid, formerly Customization › Glass & Surfaces) plus full image
// wallpapers — the five shipped Eclipse SVGs and a user's own picture.
//
// Why its own store instead of the theme store: the theme is dark-mode-scoped
// tokens and a draft/preview apply model; a background is a single, immediately
// applied preference with its own (potentially large) payload. Keeping it
// separate lets the General tab stay simple and keeps theme previews from
// touching the wallpaper.
//
// Persistence split:
//   * Small prefs + the *reference* to a custom image → localStorage (`be_background_v1`).
//   * The custom image bytes → IndexedDB (`be_background` / `custom`), so a
//     full-res wallpaper never eats the ~5 MB localStorage budget shared with
//     themes and chats.
//
// The applied values are pure CSS custom properties (not a stylesheet), so they
// do not fight the theme's managed `<style id="eclipse-theme-overrides">`.
// Resolution: `pattern` mode keeps the theme's pattern on the shell (app-wide);
// `image` mode suppresses the pattern and feeds a full-viewport `.app-bg-layer`
// that `stock-chat.tsx` renders on the ChatBot landing only.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import { pageBackgroundImage } from '@/lib/theme/tokens';
import { useThemeStore } from '@/lib/theme/store';

// ── Model ────────────────────────────────────────────────────────────────────

/** What kind of backdrop is active. */
export type BackgroundMode = 'none' | 'pattern' | 'image';
/** The shipped pattern treatment (kept in sync with `ThemeBackground`). */
export type BackgroundPattern = 'solid' | 'gradient' | 'grid';
/** How the image fills its box. */
export type BackgroundFit = 'cover' | 'contain' | 'tile';
/** Preset id, or `custom` when the user's own image is active. */
export type BackgroundPresetId = string;

export interface BackgroundPrefs {
  mode: BackgroundMode;
  pattern: BackgroundPattern;
  /** A shipped id (`eclipse-1`/`eclipse-4`/`eclipse-5`), or `custom`. */
  preset: BackgroundPresetId;
  /** Non-empty only for `preset: 'custom'`; a key into the custom-image store. */
  customKey: string;
  fit: BackgroundFit;
  /** Scrim strength over the image, 0–100, so text stays legible on any art. */
  dim: number;
}

export const DEFAULT_BACKGROUND: BackgroundPrefs = {
  // The shipped Eclipse I wallpaper ships on by default. It paints on the
  // ChatBot page only; every other tab keeps the plain themed surface.
  mode: 'image',
  pattern: 'solid',
  preset: 'eclipse-1',
  customKey: '',
  fit: 'cover',
  dim: 45,
};

const MODES: readonly BackgroundMode[] = ['none', 'pattern', 'image'];
const PATTERNS: readonly BackgroundPattern[] = ['solid', 'gradient', 'grid'];
const FITS: readonly BackgroundFit[] = ['cover', 'contain', 'tile'];

export const BACKGROUND_MODE_OPTIONS: { id: BackgroundMode; label: string; hint: string }[] = [
  { id: 'none', label: 'None', hint: 'Plain theme color — no artwork' },
  { id: 'pattern', label: 'Pattern', hint: 'Gradient or grid tinted by your brand' },
  { id: 'image', label: 'Image', hint: 'A shipped or custom wallpaper' },
];

export const BACKGROUND_PATTERN_OPTIONS: { id: BackgroundPattern; label: string; hint: string }[] = [
  { id: 'solid', label: 'Solid', hint: 'Single flat color' },
  { id: 'gradient', label: 'Gradient', hint: 'Soft vertical wash' },
  { id: 'grid', label: 'Grid', hint: 'Faint technical grid' },
];

export const BACKGROUND_FIT_OPTIONS: { id: BackgroundFit; label: string; hint: string }[] = [
  { id: 'cover', label: 'Cover', hint: 'Fill the screen, cropping if needed' },
  { id: 'contain', label: 'Contain', hint: 'Fit the whole image, letterboxed' },
  { id: 'tile', label: 'Tile', hint: 'Repeat the image at its native size' },
];

/** A shipped wallpaper. `url` is the public path (spaces encoded). */
export interface BackgroundAsset {
  id: string;
  label: string;
  url: string;
  /** Approximate file size, shown as a load-weight hint in the picker. */
  weight: string;
}

export const SHIPPED_BACKGROUNDS: BackgroundAsset[] = [
  { id: 'eclipse-1', label: 'Eclipse I', url: '/backgrounds/eclipse%20bg-1.svg', weight: '0.4 MB' },
  { id: 'eclipse-3', label: 'Eclipse III', url: '/backgrounds/eclipse%20bg-3.png', weight: '40 KB' },
  { id: 'eclipse-4', label: 'Eclipse IV', url: '/backgrounds/eclipse%20bg-4.svg', weight: '2.6 MB' },
  { id: 'eclipse-5', label: 'Eclipse V', url: '/backgrounds/eclipse%20bg-5.svg', weight: '0.9 MB' },
];

export const CUSTOM_BACKGROUND_ID = 'custom';

export function shippedBackground(id: string): BackgroundAsset | undefined {
  return SHIPPED_BACKGROUNDS.find((b) => b.id === id);
}

// ── Persistence (localStorage: prefs; IndexedDB: custom bytes) ───────────────

export const BACKGROUND_STORAGE_KEY = 'be_background_v1';
const IDB_NAME = 'be_background';
const IDB_STORE = 'custom';
const IDB_KEY = 'active';

export function normalizeBackgroundPrefs(raw: unknown): BackgroundPrefs {
  const value = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
  const mode = MODES.includes(value.mode as BackgroundMode)
    ? (value.mode as BackgroundMode)
    : DEFAULT_BACKGROUND.mode;
  const pattern = PATTERNS.includes(value.pattern as BackgroundPattern)
    ? (value.pattern as BackgroundPattern)
    : DEFAULT_BACKGROUND.pattern;
  const preset = typeof value.preset === 'string' && value.preset.length > 0
    ? value.preset
    : DEFAULT_BACKGROUND.preset;
  const customKey = typeof value.customKey === 'string' ? value.customKey : '';
  const fit = FITS.includes(value.fit as BackgroundFit)
    ? (value.fit as BackgroundFit)
    : DEFAULT_BACKGROUND.fit;
  const dim = typeof value.dim === 'number' && Number.isFinite(value.dim)
    ? Math.min(100, Math.max(0, Math.round(value.dim)))
    : DEFAULT_BACKGROUND.dim;
  return { mode, pattern, preset, customKey, fit, dim };
}

export function loadBackgroundPrefs(): BackgroundPrefs {
  if (typeof window === 'undefined') return DEFAULT_BACKGROUND;
  try {
    const raw = window.localStorage.getItem(BACKGROUND_STORAGE_KEY);
    if (!raw) return DEFAULT_BACKGROUND;
    return normalizeBackgroundPrefs(JSON.parse(raw));
  } catch {
    return DEFAULT_BACKGROUND;
  }
}

function persistBackgroundPrefs(prefs: BackgroundPrefs): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(BACKGROUND_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

function openDb(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === 'undefined') return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(IDB_STORE)) db.createObjectStore(IDB_STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

/** Read the stored custom image data URL, or null when none is present. */
export async function loadCustomImage(): Promise<string | null> {
  const db = await openDb();
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const tx = db.transaction(IDB_STORE, 'readonly');
      const req = tx.objectStore(IDB_STORE).get(IDB_KEY);
      req.onsuccess = () => resolve(typeof req.result === 'string' ? req.result : null);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

/** Store (or, with null, delete) the custom image data URL. */
export async function saveCustomImage(dataUrl: string | null): Promise<boolean> {
  const db = await openDb();
  if (!db) return false;
  return new Promise((resolve) => {
    try {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      const store = tx.objectStore(IDB_STORE);
      if (dataUrl) store.put(dataUrl, IDB_KEY);
      else store.delete(IDB_KEY);
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => resolve(false);
    } catch {
      resolve(false);
    }
  });
}

// ── Image optimisation (client-side, before storing) ─────────────────────────
// Users add a picture straight off their computer; phone photos can be 10–20 MB.
// We downscale on a canvas to a wallpaper-sized edge and re-encode, so the
// stored payload stays small. SVG/GIF (vector/animated) are passed through.

const MAX_EDGE = 2560;
const MAX_BYTES = 4_000_000;
export const MAX_UPLOAD_BYTES = 30_000_000;

export function isVectorImage(type: string, name: string): boolean {
  return type === 'image/svg+xml' || /\.svg$/i.test(name);
}

/** Re-encode an image file to a downscaled, compressed data URL (or original). */
export function optimizeImageFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read the file.'));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string') {
        reject(new Error('Could not read the file.'));
        return;
      }
      // Vector or animated art must not be rasterised.
      if (isVectorImage(file.type, file.name)) {
        resolve(result);
        return;
      }
      const img = new Image();
      img.onerror = () => resolve(result);
      img.onload = () => {
        try {
          const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
          const w = Math.max(1, Math.round(img.width * scale));
          const h = Math.max(1, Math.round(img.height * scale));
          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d');
          if (!ctx) {
            resolve(result);
            return;
          }
          ctx.drawImage(img, 0, 0, w, h);
          const isPng = file.type === 'image/png';
          const out = canvas.toDataURL(isPng ? 'image/png' : 'image/jpeg', isPng ? undefined : 0.85);
          resolve(out.length > 0 ? out : result);
        } catch {
          resolve(result);
        }
      };
      img.src = result;
    };
    reader.readAsDataURL(file);
  });
}

/** Guard the stored payload after optimisation; returns a friendly error. */
export function customImageError(dataUrl: string): string | null {
  if (dataUrl.startsWith('data:image/svg')) return null;
  if (dataUrl.length > MAX_BYTES * 1.4) {
    return 'That image is still too large after optimisation. Try a smaller picture.';
  }
  return null;
}

// ── CSS resolution ───────────────────────────────────────────────────────────

export interface BackgroundCss {
  /** `background-image` for the host element's *image* layer (`--app-bg-image`). */
  image: string;
  /** `background-image` for the host element's *pattern* layer (`--page-bg-image`). */
  pageImage: string;
  /** `background-size` for the image layer. */
  size: string;
  /** `background-repeat` for the image layer. */
  repeat: string;
  /** `background-position` for the image layer. */
  position: string;
  /** Whether a scrim should be rendered (image modes only). */
  scrim: boolean;
  /**
   * Scrim as a valid `background-image` *layer*. A bare color is not a valid
   * `background-image` value and would invalidate the whole multi-layer
   * declaration, so this is a solid-color linear-gradient instead.
   */
  scrimImage: string;
}

function sizeForFit(fit: BackgroundFit): string {
  return fit === 'cover' ? 'cover' : fit === 'contain' ? 'contain' : 'auto';
}

function scrimColorFor(dim: number): string {
  const a = Math.min(1, Math.max(0, dim / 100));
  return `rgba(0,0,0,${a})`;
}

/** A scrim that is valid inside `background-image` (a color is not). */
function scrimImageFor(dim: number): string {
  return `linear-gradient(${scrimColorFor(dim)}, ${scrimColorFor(dim)})`;
}

/**
 * Resolve prefs + the custom data URL into the concrete CSS a wallpaper layer
 * needs. `patternImage` is the theme-tinted CSS from `@/lib/theme/tokens`.
 *
 * Semantics:
 *   * `none`    → no overrides; the theme's own pattern applies.
 *   * `pattern` → the theme pattern stays on the shell (app-wide); the layer
 *                 is emptied.
 *   * `image`   → the theme pattern is suppressed so the wallpaper reads clean,
 *                 and the wallpaper layer is fed the image + scrim.
 */
export function resolveBackgroundCss(
  prefs: BackgroundPrefs,
  patternImage: string,
  customUrl: string | null,
): BackgroundCss {
  const scrimImage = scrimImageFor(prefs.dim);
  if (prefs.mode === 'pattern') {
    return {
      image: 'none',
      pageImage: patternImage !== 'none' ? patternImage : 'none',
      size: 'auto',
      repeat: 'repeat',
      position: 'center',
      scrim: false,
      scrimImage,
    };
  }
  if (prefs.mode === 'image') {
    const asset = prefs.preset === CUSTOM_BACKGROUND_ID ? null : shippedBackground(prefs.preset);
    const url = asset?.url ?? (customUrl || null);
    if (!url) {
      return { image: 'none', pageImage: 'none', size: 'auto', repeat: 'no-repeat', position: 'center', scrim: false, scrimImage };
    }
    return {
      image: `url("${url}")`,
      // Suppress the theme pattern so the wallpaper is the only backdrop.
      pageImage: 'none',
      size: sizeForFit(prefs.fit),
      repeat: prefs.fit === 'tile' ? 'repeat' : 'no-repeat',
      position: 'center',
      scrim: true,
      scrimImage,
    };
  }
  return { image: 'none', pageImage: 'none', size: 'auto', repeat: 'no-repeat', position: 'center', scrim: false, scrimImage };
}

// ── DOM application ──────────────────────────────────────────────────────────

/**
 * Push the resolved background onto the document as CSS variables. Purely a
 * custom-property write (no stylesheet), so it composes with the theme store's
 * managed `<style>` and survives theme changes. `--page-bg-image` is overridden
 * only to suppress the theme pattern in image mode; for `none`/`pattern` it is
 * removed so the theme's own value (or the shipped default) takes over.
 */
export function applyBackgroundToDocument(prefs: BackgroundPrefs, patternImage: string, customUrl: string | null): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (prefs.mode === 'none' || prefs.mode === 'pattern') {
    clearBackgroundFromDocument();
    return;
  }
  const css = resolveBackgroundCss(prefs, patternImage, customUrl);
  root.style.setProperty('--page-bg-image', css.pageImage);
  root.style.setProperty('--app-bg-image', css.image);
  root.style.setProperty('--app-bg-size', css.size);
  root.style.setProperty('--app-bg-repeat', css.repeat);
  root.style.setProperty('--app-bg-position', css.position);
  root.style.setProperty('--app-bg-scrim', css.scrim ? css.scrimImage : 'none');
}

function clearBackgroundFromDocument(): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  for (const name of [
    '--page-bg-image', '--app-bg-image', '--app-bg-size', '--app-bg-repeat', '--app-bg-position', '--app-bg-scrim',
  ]) {
    root.style.removeProperty(name);
  }
}

/** The theme-tinted pattern CSS for a pattern id (brand is read per-hydrate). */
function patternCssFor(prefs: BackgroundPrefs): string {
  const brand = readBrandRgb();
  return pageBackgroundImage(prefs.pattern, brand);
}

/** Read the live `--brand` color (falls back to the Eclipse green). */
function readBrandRgb(): string {
  if (typeof document === 'undefined') return '#7aff78';
  const hex = getComputedStyle(document.documentElement).getPropertyValue('--brand').trim();
  return /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(hex) ? hex : '#7aff78';
}

// ── Store ────────────────────────────────────────────────────────────────────

export interface BackgroundStore {
  prefs: BackgroundPrefs;
  hydrated: boolean;
  /** The custom image data URL, once loaded from IndexedDB. */
  customUrl: string | null;
  /** True while saving an upload to IndexedDB. */
  saving: boolean;
  hydrate: () => Promise<void>;
  /** Patch prefs; applies immediately and (for pattern/image) persists. */
  setPrefs: (patch: Partial<BackgroundPrefs>) => void;
  /** Optimise + store a user image and switch to it. Returns an error string. */
  setCustomImage: (file: File) => Promise<string | null>;
  /** Forget the stored custom image and fall back to a shipped preset. */
  clearCustomImage: () => Promise<void>;
  /** Restore shipped defaults. */
  reset: () => void;
}

export const useBackgroundStore = create<BackgroundStore>((set, get) => {
  /** Apply + persist the current prefs. */
  const apply = (prefs: BackgroundPrefs, customUrl = get().customUrl) => {
    applyBackgroundToDocument(prefs, patternCssFor(prefs), customUrl);
  };

  const commit = (patch: Partial<BackgroundPrefs>) => {
    const next = normalizeBackgroundPrefs({ ...get().prefs, ...patch });
    set({ prefs: next });
    persistBackgroundPrefs(next);
    apply(next);
  };

  return {
    prefs: DEFAULT_BACKGROUND,
    hydrated: false,
    customUrl: null,
    saving: false,

    hydrate: async () => {
      const prefs = loadBackgroundPrefs();
      let customUrl: string | null = null;
      if (prefs.mode === 'image' && prefs.preset === CUSTOM_BACKGROUND_ID) {
        customUrl = await loadCustomImage();
      }
      set({ prefs, customUrl, hydrated: true });
      apply(prefs, customUrl);
    },

    setPrefs: (patch) => commit(patch),

    setCustomImage: async (file) => {
      if (file.size > MAX_UPLOAD_BYTES) {
        return 'That image is larger than 30 MB. Please choose a smaller picture.';
      }
      set({ saving: true });
      try {
        const dataUrl = await optimizeImageFile(file);
        const error = customImageError(dataUrl);
        if (error) return error;
        const ok = await saveCustomImage(dataUrl);
        if (!ok) return 'Could not store the image on this device (storage unavailable).';
        set({ customUrl: dataUrl, saving: false });
        commit({ mode: 'image', preset: CUSTOM_BACKGROUND_ID });
        return null;
      } catch (err) {
        set({ saving: false });
        return err instanceof Error ? err.message : 'Could not process that image.';
      }
    },

    clearCustomImage: async () => {
      await saveCustomImage(null);
      set({ customUrl: null });
      if (get().prefs.preset === CUSTOM_BACKGROUND_ID) {
        commit({ preset: DEFAULT_BACKGROUND.preset, mode: 'pattern' });
      }
    },

    reset: () => {
      set({ prefs: DEFAULT_BACKGROUND, customUrl: get().customUrl });
      persistBackgroundPrefs(DEFAULT_BACKGROUND);
      apply(DEFAULT_BACKGROUND);
    },
  };
});

/**
 * Hydrate the background from storage and apply it, once, client-side. Also
 * re-applies when the theme changes, because pattern mode derives its tint from
 * the live `--brand` color (read after the theme store has written it).
 */
export function useHydrateBackground() {
  const hydrate = useBackgroundStore((s) => s.hydrate);
  const hydrated = useBackgroundStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) void hydrate();
  }, [hydrated, hydrate]);

  useEffect(() => {
    if (!hydrated) return;
    const apply = () => {
      const s = useBackgroundStore.getState();
      applyBackgroundToDocument(s.prefs, patternCssFor(s.prefs), s.customUrl);
    };
    apply();
    return useThemeStore.subscribe(apply);
  }, [hydrated]);
}

/** True when any non-default backdrop is configured (drives the "Custom" badge). */
export function isBackgroundCustomized(prefs: BackgroundPrefs): boolean {
  return prefs.mode !== DEFAULT_BACKGROUND.mode;
}

export { clearBackgroundFromDocument };
