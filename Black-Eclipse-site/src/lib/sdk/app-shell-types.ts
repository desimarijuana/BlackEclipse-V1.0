// ── App shell contracts (shared by the Next route and the client) ────────────
// The navigation config is app-wide, not per-browser: a `SystemConfig` row holds
// the order/visibility of the fixed sidebar sections plus the active nav mode.
// The Python runtime never owns this state; it reaches the Next routes over the
// same loopback callback the theme tools use.
//
// This module is deliberately dependency-free (types + pure normalization) so
// both the server route and the client store can import it without pulling in
// Prisma or React.

import type { AppTab } from '@/lib/app-tabs';

export type AppNavMode = 'terminal' | 'agentic' | 'bots' | 'graph';

export const APP_NAV_MODES: readonly AppNavMode[] = ['terminal', 'agentic', 'bots', 'graph'];

export type AppNavGroup = 'terminal' | 'agentic' | 'bots' | 'graph' | 'both';

export interface AppNavSection {
  id: AppTab;
  enabled: boolean;
}

export interface AppNavConfig {
  sections: AppNavSection[];
  mode: AppNavMode;
}

/** The fixed sidebar sections, in the shipped default order. */
export interface AppNavManifestSection {
  id: AppTab;
  label: string;
  group: AppNavGroup;
}

export const APP_NAV_SECTIONS: readonly AppNavManifestSection[] = [
  { id: 'chat', label: 'ChatBot', group: 'both' },
  { id: 'home', label: 'Dashboard', group: 'terminal' },
  { id: 'dashboard', label: 'Command Center', group: 'terminal' },
  { id: 'investor-eye', label: 'Investor Eye', group: 'terminal' },
  { id: 'market-workspace', label: 'Chart Workspace', group: 'terminal' },
  { id: 'discovery', label: 'Market Discover', group: 'terminal' },
  { id: 'portfolio', label: 'Portfolio', group: 'terminal' },
  { id: 'journal', label: 'Journal', group: 'terminal' },
  { id: 'news', label: 'Market News', group: 'terminal' },
  { id: 'heatmap', label: 'Market Bubbles', group: 'terminal' },
  { id: 'economics', label: 'Economics', group: 'terminal' },
  { id: 'alerts', label: 'Price Alerts', group: 'terminal' },
  { id: 'skills', label: 'Skills', group: 'agentic' },
  { id: 'sdk', label: 'Eclipse SDK', group: 'agentic' },
  { id: 'memory', label: 'Eclipse Memory', group: 'agentic' },
  { id: 'artifacts', label: 'Artifacts', group: 'agentic' },
  { id: 'graph-studio', label: 'Graph Studio', group: 'graph' },
];

export const APP_NAV_IDS: readonly AppTab[] = APP_NAV_SECTIONS.map((section) => section.id);

/** A navigation target the shell can open. */
export interface AppNavigateTarget {
  tab: AppTab;
  page?: string;
  dashboardId?: string;
  subroute?: string;
  params?: Record<string, string>;
}

export interface AppShellState {
  revision: number;
  initialized: boolean;
  updatedAt: string;
  nav: AppNavConfig;
}

export interface AppShellResponse extends AppShellState {
  success?: boolean;
  sections: readonly AppNavManifestSection[];
  modes: readonly AppNavMode[];
}

export interface AppNavPatch {
  sections?: AppNavSection[];
  mode?: AppNavMode;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function isAppNavMode(value: unknown): value is AppNavMode {
  return typeof value === 'string' && (APP_NAV_MODES as readonly string[]).includes(value);
}

function isAppTab(value: unknown): value is AppTab {
  return typeof value === 'string' && (APP_NAV_IDS as readonly string[]).includes(value);
}

export function defaultAppNav(): AppNavConfig {
  return {
    sections: APP_NAV_SECTIONS.map((section) => ({ id: section.id, enabled: true })),
    mode: 'terminal',
  };
}

/**
 * Normalize an incoming nav patch/state. Unknown ids are dropped, duplicates
 * collapse to their first occurrence, and every known section missing from the
 * payload is appended in canonical order. The order a caller supplies is kept.
 */
export function normalizeAppNav(raw: unknown): AppNavConfig {
  const value = isRecord(raw) ? raw : {};
  const mode = isAppNavMode(value.mode) ? value.mode : 'terminal';
  const sections: AppNavSection[] = [];
  if (Array.isArray(value.sections)) {
    for (const entry of value.sections) {
      if (!isRecord(entry) || !isAppTab(entry.id)) continue;
      if (sections.some((section) => section.id === entry.id)) continue;
      sections.push({ id: entry.id, enabled: entry.enabled !== false });
    }
  }
  const present = new Set(sections.map((section) => section.id));
  // A newly shipped section is inserted in its canonical position (right after
  // ChatBot) for an existing nav order, instead of silently landing at the end.
  if (!present.has('home')) {
    const chatIndex = sections.findIndex((section) => section.id === 'chat');
    if (chatIndex >= 0) {
      sections.splice(chatIndex + 1, 0, { id: 'home', enabled: true });
      present.add('home');
    }
  }
  for (const section of APP_NAV_SECTIONS) {
    if (!present.has(section.id)) sections.push({ id: section.id, enabled: true });
  }
  return { sections, mode };
}

/** Parse the persisted `SystemConfig` value. `null` = never initialized. */
export function parseAppShellState(raw: string | null): AppShellState {
  if (raw === null) {
    return { revision: 0, initialized: false, updatedAt: '', nav: defaultAppNav() };
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!isRecord(parsed)) {
      return { revision: 1, initialized: true, updatedAt: '', nav: defaultAppNav() };
    }
    const revision = typeof parsed.revision === 'number' && Number.isInteger(parsed.revision) && parsed.revision > 0
      ? parsed.revision
      : 1;
    return {
      revision,
      initialized: true,
      updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : '',
      nav: normalizeAppNav(parsed.nav ?? parsed),
    };
  } catch {
    return { revision: 0, initialized: false, updatedAt: '', nav: defaultAppNav() };
  }
}
