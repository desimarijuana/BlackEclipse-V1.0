// ── Sidebar customization store ──────────────────────────────────────────────
// Client-side zustand store holding the user's sidebar config (order,
// visibility, shortcuts) and the active nav mode. The section config is
// app-wide (JDDS `SystemConfig` via the SDK app-shell routes, with
// `localStorage` as the instant cache). The ACTIVE MODE is deliberately
// per-shell: each browser tab/window keeps its own mode in `sessionStorage`, so
// switching to Bots in one tab never drags another tab out of its mode. A fresh
// shell always starts in Terminal; a tab that already chose a mode keeps it.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import {
  assignDefaultShortcuts,
  dedupeShortcuts,
  defaultSidebarConfig,
  isNavGroup,
  loadSidebarConfig,
  saveSidebarConfig,
  type SidebarConfig,
  type NavGroup,
} from './config';
import type { AppTab } from '@/components/layout/sidebar';
import { eclipseSdk } from '@/lib/sdk';
import { normalizeAppNav, type AppNavMode, type AppShellState } from '@/lib/sdk/app-shell-types';

export interface SidebarConfigStore {
  config: SidebarConfig;
  hydrated: boolean;
  /** Desktop icon-rail preference. Shared so the Ctrl/Cmd+B shortcut and the
   *  in-sidebar chevrons are one control; the mobile drawer ignores it. */
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  toggleCollapsed: () => void;
  /** Active top-level menu mode (Terminal / Agentic / Bots / Graph). Per shell:
   *  other open tabs keep their own mode, and a remote nav update never
   *  overrides it. Keyboard shortcuts and navigation still switch it locally. */
  mode: NavGroup;
  /** Merge a hydrated config from localStorage (client only, post-mount). */
  hydrate: () => void;
  setConfig: (cfg: SidebarConfig) => void;
  setMode: (mode: NavGroup) => void;
  /** Follow the active screen without treating it as an explicit app-wide change. */
  setModeFromNavigation: (mode: NavGroup) => void;
  toggleEnabled: (id: AppTab) => void;
  setShortcut: (id: AppTab, shortcut: string) => void;
  /** Move an item from one index to another (reorder). */
  move: (from: number, to: number) => void;
  reset: () => void;
  /** Apply an app-wide state pushed by the SDK route/SSE. Never echoes back. */
  applyRemoteState: (state: AppShellState) => void;
}

/** Persisted top-level menu mode — the shared seed for newly opened shells. */
export const SIDEBAR_MODE_KEY = 'be_sidebar_mode_v1';
/** This tab's own mode. `sessionStorage` is per browser tab/window. */
export const SIDEBAR_TAB_MODE_KEY = 'be_sidebar_tab_mode_v1';
/** Desktop sidebar collapse preference (presentation only, localStorage). */
export const SIDEBAR_COLLAPSED_KEY = 'be_sidebar_collapsed_v1';

function readStoredCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  // The desktop shell's frameless window always opens with the FULL sidebar.
  // The icon rail stays available at runtime (Ctrl/Cmd+B), but a collapsed state
  // from an earlier session must not shrink the sidebar on launch — that is what
  // made the desktop app look like it was missing its sidebar.
  const bridge = window as unknown as { __TAURI__?: unknown; __TAURI_INTERNALS__?: unknown };
  if (bridge.__TAURI__ || bridge.__TAURI_INTERNALS__) return false;
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

function writeStoredCollapsed(collapsed: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0');
  } catch {
    /* private mode / storage disabled — the in-memory value still works */
  }
}

function readStoredMode(storage: 'local' | 'session'): NavGroup | null {
  if (typeof window === 'undefined') return null;
  try {
    const store = storage === 'session' ? window.sessionStorage : window.localStorage;
    const saved = store.getItem(storage === 'session' ? SIDEBAR_TAB_MODE_KEY : SIDEBAR_MODE_KEY);
    return isNavGroup(saved) ? saved : null;
  } catch {
    return null;
  }
}

function writeStoredMode(storage: 'local' | 'session', mode: NavGroup): void {
  if (typeof window === 'undefined') return;
  try {
    const store = storage === 'session' ? window.sessionStorage : window.localStorage;
    store.setItem(storage === 'session' ? SIDEBAR_TAB_MODE_KEY : SIDEBAR_MODE_KEY, mode);
  } catch {
    /* private mode / storage disabled — the in-memory mode still works */
  }
}

interface NavPayload {
  sections: Array<{ id: AppTab; enabled: boolean }>;
  mode: AppNavMode;
}

function navPayload(config: SidebarConfig, mode: NavGroup): NavPayload {
  return {
    sections: config.sections.map((section) => ({ id: section.id, enabled: section.enabled })),
    mode,
  };
}

let syncTimer: ReturnType<typeof setTimeout> | null = null;
let lastSyncedPayload: string | null = null;
let remoteLoaded = false;
// Navigation follows the active screen locally; only the switcher/hotkeys are
// explicit app-wide mode changes worth an audit entry.
let suppressModeSync = false;

/**
 * Push a local nav change app-wide (debounced). The echo from our own PUT is
 * suppressed by `lastSyncedPayload`, so SSE does not fight the user's edit.
 */
function scheduleNavSync(config: SidebarConfig, mode: NavGroup): void {
  if (typeof window === 'undefined') return;
  const payload = navPayload(config, mode);
  const key = JSON.stringify(payload);
  if (key === lastSyncedPayload) return;
  if (syncTimer) clearTimeout(syncTimer);
  syncTimer = setTimeout(() => {
    const current = useSidebarConfigStore.getState();
    const next = navPayload(current.config, current.mode);
    const nextKey = JSON.stringify(next);
    if (nextKey === lastSyncedPayload) return;
    lastSyncedPayload = nextKey;
    void eclipseSdk.app.update(next).catch(() => {
      // Allow a later edit to retry; the local cache remains authoritative.
      if (lastSyncedPayload === nextKey) lastSyncedPayload = null;
    });
  }, 500);
}

async function loadRemoteNav(config: SidebarConfig, mode: NavGroup): Promise<void> {
  try {
    const state = await eclipseSdk.app.get();
    if (state.initialized) {
      useSidebarConfigStore.getState().applyRemoteState(state);
    } else {
      // First run with the app-wide store: migrate the browser's existing
      // arrangement up once, exactly like the theme's local→server migration.
      const payload = navPayload(config, mode);
      lastSyncedPayload = JSON.stringify(payload);
      await eclipseSdk.app.update(payload).catch(() => undefined);
    }
  } catch {
    /* app route unavailable — keep the local cache */
  } finally {
    remoteLoaded = true;
  }
}

export const useSidebarConfigStore = create<SidebarConfigStore>((set, get) => ({
  // SSR-consistent default; the real config is loaded on mount (avoids
  // hydration mismatch warnings).
  config: defaultSidebarConfig(),
  hydrated: false,
  collapsed: false,
  mode: 'terminal',

  hydrate: () => {
    const config = loadSidebarConfig();
    saveSidebarConfig(config);
    // This tab's own mode wins; a fresh shell always starts in Terminal.
    const mode = readStoredMode('session') ?? 'terminal';
    writeStoredMode('session', mode);
    set({ config, hydrated: true, mode, collapsed: readStoredCollapsed() });
    void loadRemoteNav(config, mode);
  },

  setCollapsed: (collapsed) => {
    writeStoredCollapsed(collapsed);
    set({ collapsed });
  },

  toggleCollapsed: () => {
    const collapsed = !get().collapsed;
    writeStoredCollapsed(collapsed);
    set({ collapsed });
  },

  applyRemoteState: (state) => {
    const nav = normalizeAppNav(state.nav);
    const current = useSidebarConfigStore.getState();
    const customized = current.config.shortcutsCustomized === true;
    const shortcuts = new Map(current.config.sections.map((section) => [section.id, section.shortcut] as const));
    const mapped = nav.sections.map((section) => ({
      id: section.id,
      enabled: section.enabled,
      shortcut: shortcuts.get(section.id) ?? '',
    }));
    // The app-wide store orders sections but never ships shortcuts (those stay
    // local). Re-number the default scheme against the order we just adopted so
    // the menu still reads F1..F12; keep a deliberate custom mapping intact.
    const sections = customized ? dedupeShortcuts(mapped) : assignDefaultShortcuts(mapped);
    // Sections are app-wide; the mode is not. Keep this shell's mode and only
    // refresh the shared seed a newly opened shell could inspect.
    const remoteMode: NavGroup = isNavGroup(nav.mode) ? nav.mode : current.mode;
    const mode = current.mode;
    const config: SidebarConfig = { sections, shortcutVersion: 3, shortcutsCustomized: customized };
    saveSidebarConfig(config);
    writeStoredMode('local', remoteMode);
    writeStoredMode('session', mode);
    lastSyncedPayload = JSON.stringify(navPayload(config, mode));
    set({ config, mode, hydrated: true });
  },

  setConfig: (config) => {
    saveSidebarConfig(config);
    set({ config });
  },

  setMode: (mode) => {
    if (get().mode === mode) return;
    suppressModeSync = false;
    writeStoredMode('session', mode);
    writeStoredMode('local', mode);
    set({ mode });
  },

  setModeFromNavigation: (mode) => {
    if (get().mode === mode) return;
    suppressModeSync = true;
    writeStoredMode('session', mode);
    writeStoredMode('local', mode);
    set({ mode });
  },

  toggleEnabled: (id) =>
    set((s) => {
      const config: SidebarConfig = {
        ...s.config,
        sections: s.config.sections.map((x) => (x.id === id ? { ...x, enabled: !x.enabled } : x)),
      };
      saveSidebarConfig(config);
      return { config };
    }),

  setShortcut: (id, shortcut) =>
    set((s) => {
      // A key can only open one tab — assigning it here clears it elsewhere.
      // The explicit choice opts the user out of the shipped F1..F12 re-numbering.
      const config: SidebarConfig = {
        ...s.config,
        shortcutsCustomized: true,
        sections: s.config.sections.map((x) => {
          if (x.id === id) return { ...x, shortcut };
          return x.shortcut === shortcut && shortcut !== '' ? { ...x, shortcut: '' } : x;
        }),
      };
      saveSidebarConfig(config);
      return { config };
    }),

  move: (from, to) =>
    set((s) => {
      const sections = [...s.config.sections];
      if (from < 0 || to < 0 || from >= sections.length || to >= sections.length || from === to) {
        return {};
      }
      const [item] = sections.splice(from, 1);
      sections.splice(to, 0, item);
      // The default scheme is positional: moving a row re-numbers the slots so
      // the menu still reads F1..F12 top to bottom. Custom keys keep their tab.
      const config: SidebarConfig = {
        ...s.config,
        sections: s.config.shortcutsCustomized ? sections : assignDefaultShortcuts(sections),
      };
      saveSidebarConfig(config);
      return { config };
    }),

  reset: () => {
    const config = defaultSidebarConfig();
    saveSidebarConfig(config);
    set({ config });
  },
}));

// Local edits are mirrored app-wide once the remote state has been read (or
// migrated). Remote applies set `lastSyncedPayload`, so they are not echoed.
useSidebarConfigStore.subscribe((state, prev) => {
  if (!remoteLoaded) return;
  if (state.config === prev.config && state.mode === prev.mode) return;
  if (suppressModeSync) {
    suppressModeSync = false;
    if (state.config === prev.config) return;
  }
  scheduleNavSync(state.config, state.mode);
});

/** Hydrate the sidebar config from localStorage once, on the client. */
export function useHydrateSidebarConfig() {
  const hydrate = useSidebarConfigStore((s) => s.hydrate);
  const hydrated = useSidebarConfigStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
