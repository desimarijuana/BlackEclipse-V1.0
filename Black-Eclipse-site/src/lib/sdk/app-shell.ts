// ── App shell state (server-only) ────────────────────────────────────────────
// Persists the app-wide navigation order/visibility and nav mode in JDDS
// `SystemConfig`, and broadcasts updates to connected shells. The client keeps
// a localStorage cache for instant paint; this row is the source of truth once
// initialized, mirroring the app-wide theme.
//
// Server-only: imports the Prisma-backed settings vault. The route layer
// (`app-server.ts`) is the HTTP seam; the client store talks to it over fetch.

import { getConfig, setConfig } from '@/lib/settings';
import {
  defaultAppNav,
  normalizeAppNav,
  parseAppShellState,
  type AppNavigateTarget,
  type AppShellState,
} from './app-shell-types';

export const APP_SHELL_CONFIG_KEY = 'eclipse_app_shell_nav';

export type AppShellEvent =
  | { type: 'nav'; state: AppShellState }
  | { type: 'navigate'; target: AppNavigateTarget };

type Listener = (event: AppShellEvent) => void;

const listeners = new Set<Listener>();

export function subscribeAppShell(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function emit(event: AppShellEvent): void {
  for (const listener of listeners) {
    try {
      listener(event);
    } catch {
      /* one broken stream must not stop the others */
    }
  }
}

export async function getAppShellState(): Promise<AppShellState> {
  return parseAppShellState(await getConfig(APP_SHELL_CONFIG_KEY));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/** Apply a partial nav patch, bump the revision, persist and broadcast. */
export async function updateAppShellNav(patch: unknown): Promise<AppShellState> {
  const current = await getAppShellState();
  const raw = isRecord(patch) && isRecord(patch.nav) ? patch.nav : patch;
  const value = isRecord(raw) ? raw : {};
  const nav = normalizeAppNav({
    sections: value.sections !== undefined ? value.sections : current.nav.sections,
    mode: value.mode !== undefined ? value.mode : current.nav.mode,
  });
  const state: AppShellState = {
    revision: current.revision + 1,
    initialized: true,
    updatedAt: new Date().toISOString(),
    nav,
  };
  await setConfig(APP_SHELL_CONFIG_KEY, JSON.stringify({
    revision: state.revision,
    updatedAt: state.updatedAt,
    nav: state.nav,
  }));
  emit({ type: 'nav', state });
  return state;
}

/** Reset the nav to the shipped order/mode; broadcast the reset state. */
export async function resetAppShellNav(): Promise<AppShellState> {
  const current = await getAppShellState();
  const state: AppShellState = {
    revision: current.revision + 1,
    initialized: true,
    updatedAt: new Date().toISOString(),
    nav: defaultAppNav(),
  };
  await setConfig(APP_SHELL_CONFIG_KEY, JSON.stringify({
    revision: state.revision,
    updatedAt: state.updatedAt,
    nav: state.nav,
  }));
  emit({ type: 'nav', state });
  return state;
}

/** Broadcast a navigation command to every connected shell. */
export function publishNavigation(target: AppNavigateTarget): void {
  emit({ type: 'navigate', target });
}
