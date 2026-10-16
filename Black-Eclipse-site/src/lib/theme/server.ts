// ── Eclipse theme — server-side (app-wide) persistence ───────────────────────
// The user's theme is an APP-WIDE property, not a per-browser one. It is stored
// in JDDS `SystemConfig` so every browser ORIGIN and every device renders the
// same look. `localStorage` (see `store.ts`) remains only a per-origin cache for
// instant first paint; this table is the source of truth, read/written through
// the `/api/theme` route.
//
// Server-only: this module imports the Prisma-backed settings vault, so it must
// never be pulled into a client bundle. The client store talks to it over HTTP.
import { getConfig, setConfig } from '@/lib/settings';
import { normalizeTheme, type EclipseTheme } from './tokens';

/** `SystemConfig` key holding the single app-wide theme JSON. */
export const THEME_CONFIG_KEY = 'eclipse_theme';

export interface ServerThemeState {
  /** The saved theme, or null when the app-wide look is the shipped default. */
  theme: EclipseTheme | null;
  /**
   * Whether the app-wide theme has ever been set (including an explicit Reset).
   * `false` means the row has never existed — the client uses that to MIGRATE a
   * pre-existing per-origin `localStorage` theme up to the server (one time)
   * instead of wiping it. `true` with a null theme means an explicit Reset, which
   * the client honours by clearing its local override.
   */
  initialized: boolean;
}

/** Read the app-wide theme plus whether it has been initialized. */
export async function getServerThemeState(): Promise<ServerThemeState> {
  const raw = await getConfig(THEME_CONFIG_KEY);
  if (raw === null) return { theme: null, initialized: false };
  try {
    const parsed = JSON.parse(raw);
    if (!parsed) return { theme: null, initialized: true }; // explicit reset
    return { theme: normalizeTheme(parsed), initialized: true };
  } catch {
    return { theme: null, initialized: true };
  }
}

/** The saved app-wide theme, or null when the default applies. */
export async function getServerTheme(): Promise<EclipseTheme | null> {
  return (await getServerThemeState()).theme;
}

/** Persist a theme as the app-wide theme; returns the normalized theme. */
export async function setServerTheme(raw: unknown): Promise<EclipseTheme> {
  const theme = normalizeTheme(raw);
  await setConfig(THEME_CONFIG_KEY, JSON.stringify(theme));
  return theme;
}

/**
 * Reset the app-wide theme to the shipped default. Stores JSON `null` (rather
 * than deleting the row) so the client can tell "explicitly reset" apart from
 * "never initialized" and won't migrate a stale local theme back.
 */
export async function clearServerTheme(): Promise<void> {
  await setConfig(THEME_CONFIG_KEY, 'null');
}
