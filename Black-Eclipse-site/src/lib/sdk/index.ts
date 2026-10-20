// ── Eclipse SDK — the typed user-facing extension client ─────────────────────
// ONE importable surface for composing Eclipse from the browser (and from the
// SDK screen / browser console):
//
//   eclipseSdk.widgets.create({ label, primitive, source })
//   eclipseSdk.pages.create({ title, widgets: [...] })
//   eclipseSdk.portfolio.createFund({ name, goal })
//   eclipseSdk.portfolio.addStock(portfolioId, { symbol, quantity, price })
//   eclipseSdk.design.apply({ colors: { primary: '#77edfd' } })
//   eclipseSdk.locks.create({ resourceType: 'page', resourceId, passphrase })
//   eclipseSdk.locks.unlock(lockId, passphrase)   // then mutations carry the token
//
// Client-safe: fetch only. The Next route (`/api/sdk/**`) is the transport; the
// Python runtime is the authority for everything except the app-wide theme.

import type { EclipseTheme } from '@/lib/theme/tokens';
import type { ThemeSpec } from './theme-spec';
import type { AppNavigateTarget, AppNavPatch, AppShellResponse } from './app-shell-types';
import { navigateTo } from './navigate';
export type { ThemeSpec } from './theme-spec';
export type {
  AppNavigateTarget,
  AppNavConfig,
  AppNavMode,
  AppNavPatch,
  AppNavSection,
  AppShellResponse,
} from './app-shell-types';

/** A deep-partial design patch (grouped tokens may be partially supplied). */
export type ThemePatch = Partial<Omit<EclipseTheme, 'colors' | 'glass' | 'sidebar'>> & {
  colors?: Partial<EclipseTheme['colors']>;
  glass?: Partial<EclipseTheme['glass']>;
  sidebar?: Partial<EclipseTheme['sidebar']>;
};

export interface SdkCapabilities {
  success?: boolean;
  sdkVersion: string;
  runtime: 'available' | 'unavailable' | string;
  widgets: {
    canCreate: boolean;
    canDelete?: boolean;
    count?: number;
    primitives?: string[];
    sourcePrimitives?: string[];
    componentPrefix?: string;
  };
  pages: { canCreate: boolean; canCompose?: boolean; routing?: string };
  dashboards?: {
    available: boolean;
    canMutate: boolean;
    count?: number;
    activeDashboardId?: string | null;
  };
  portfolio: {
    available: boolean;
    canAddStock: boolean;
    canCreateFund: boolean;
    fundKinds?: string[];
    portfolioCount?: number;
  };
  design: {
    canApply: boolean;
    hasSavedTheme?: boolean;
    initialized?: boolean;
    presets?: { id: string; label: string; description: string; primary: string; scheme: string }[];
  };
  locks: {
    canCreate: boolean;
    canUnlock: boolean;
    resources: string[];
    header?: string;
    count?: number;
  };
  audit?: { count?: number };
}

export type SdkWidgetPrimitive =
  | 'data-table'
  | 'metric-card'
  | 'line-chart'
  | 'area-chart'
  | 'bar-chart'
  | 'pie-chart'
  | 'clock'
  | 'list'
  | 'markdown'
  | 'status-indicator'
  | 'empty-state'
  | 'error-state'
  | 'clock';

export interface SdkWidgetRecord {
  id: string;
  componentId: string;
  slug: string;
  label: string;
  description: string;
  icon: string;
  category: string;
  primitive: SdkWidgetPrimitive;
  source?: string | null;
  surface?: 'dashboard' | 'page' | 'both';
  config: Record<string, unknown>;
  sizes: string[];
  createdAt: string;
  updatedAt: string;
}

export interface SdkWidgetInput {
  slug: string;
  label: string;
  description?: string;
  icon?: string;
  category?: string;
  primitive?: SdkWidgetPrimitive;
  source?: string;
  surface?: 'dashboard' | 'page' | 'both';
  config?: Record<string, unknown>;
  sizes?: string[];
}

export interface SdkPageWidget {
  componentId: string;
  config?: Record<string, unknown>;
  height?: number;
}

export interface SdkCreatePageInput {
  title: string;
  description?: string;
  path?: string;
  icon?: string;
  tags?: string[];
  widgets?: SdkPageWidget[];
  idempotencyKey?: string;
}

export interface SdkFund {
  id: string;
  name: string;
  baseCurrency: string;
  costBasisMethod: string;
  status?: string;
  description?: string | null;
  kind: 'fund' | 'portfolio' | string;
  metadata: {
    kind?: string;
    goal?: string | null;
    icon?: string | null;
    accent?: string | null;
    [key: string]: unknown;
  };
  createdAt: string;
  updatedAt: string;
}

export interface SdkCreateFundInput {
  name: string;
  baseCurrency?: string;
  description?: string;
  goal?: string;
  icon?: string;
  accent?: string;
  costBasisMethod?: 'FIFO' | 'LIFO' | 'AVERAGE_COST';
  metadata?: Record<string, unknown>;
}

export interface SdkAddStockInput {
  symbol: string;
  quantity: string | number;
  price?: string | number;
  currency?: string;
  type?: 'BUY' | 'TRANSFER_IN';
  tradeDate?: string;
  fees?: string | number;
  notes?: string;
}

export interface SdkLock {
  id: string;
  resourceType: 'page' | 'widget' | 'portfolio' | 'design' | 'dashboard' | 'theme';
  resourceId: string;
  label?: string | null;
  hint?: string | null;
  createdBy?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SdkCreateLockInput {
  resourceType: SdkLock['resourceType'];
  resourceId: string;
  passphrase: string;
  label?: string;
  hint?: string;
}

export interface SdkDashboardSummary {
  dashboardId: string;
  blueprintId: string;
  title: string;
  path: string;
  revision: number;
  updatedAt: string;
  widgetCount: number;
  componentIds: string[];
}

export interface SdkDashboardTarget {
  sectionId: string;
  columnId?: string;
  index?: number;
  columnIndex?: number;
}

export interface SdkDashboardTemplateSummary {
  id: string;
  name: string;
  description: string;
}

export interface SdkDashboardRevision {
  revision: number;
  summary: string;
  changes: Array<{
    type?: string;
    instanceId?: string | null;
    componentId?: string | null;
    detail?: string;
  }>;
  createdAt: string;
}

export interface SdkAuditEntry {
  id: string;
  actor?: string | null;
  action: string;
  resourceType?: string | null;
  resourceId?: string | null;
  summary: string;
  detail: Record<string, unknown>;
  createdAt: string;
}

export interface SdkAuditFilter {
  limit?: number;
  action?: string;
  resourceType?: string;
}

export interface SdkWorkspaceLayout {
  version?: number;
  sections?: unknown[];
  hiddenZones?: string[];
  zoneWidths?: Record<string, number>;
  [key: string]: unknown;
}

export interface SdkDashboardSnapshot {
  success?: boolean;
  dashboard: SdkDashboardSummary;
  blueprint: Record<string, unknown>;
  revision: number;
  layout: SdkWorkspaceLayout;
  activeDashboardId?: string | null;
}

export interface SdkDashboardAddWidgetInput {
  componentId: string;
  instanceId?: string;
  config?: Record<string, unknown>;
  target?: SdkDashboardTarget;
  zone?: 'left' | 'main' | 'right';
  height?: number;
  expectedRevision?: number;
}

export interface SdkThemePresetSummary {
  id: string;
  label: string;
  description: string;
  primary: string;
  scheme: string;
}

export interface SdkSavedThemePreset {
  name: string;
  spec: ThemeSpec;
  theme: EclipseTheme;
  createdAt: string;
  updatedAt: string;
}

export interface SdkThemeState {
  success?: boolean;
  theme: EclipseTheme;
  initialized: boolean;
  presets: SdkThemePresetSummary[];
  savedPresets: SdkSavedThemePreset[];
}

export interface SdkDesignState {
  success?: boolean;
  theme: EclipseTheme;
  initialized: boolean;
  design: SdkCapabilities['design'];
}

export class SdkError extends Error {
  status: number;
  code?: string;
  lockId?: string;
  hint?: string;

  constructor(message: string, status: number, options: { code?: string; lockId?: string; hint?: string } = {}) {
    super(message);
    this.name = 'SdkError';
    this.status = status;
    this.code = options.code;
    this.lockId = options.lockId;
    this.hint = options.hint;
  }
}

const UNLOCK_STORAGE_KEY = 'be_sdk_unlock_v1';
let unlockToken: string | null = null;

function readToken(): string | null {
  if (unlockToken) return unlockToken;
  if (typeof window === 'undefined') return null;
  try {
    unlockToken = window.sessionStorage.getItem(UNLOCK_STORAGE_KEY);
  } catch {
    unlockToken = null;
  }
  return unlockToken;
}

/** Remember an unlock token for subsequent SDK mutations. */
export function setUnlockToken(token: string | null) {
  unlockToken = token;
  if (typeof window === 'undefined') return;
  try {
    if (token) window.sessionStorage.setItem(UNLOCK_STORAGE_KEY, token);
    else window.sessionStorage.removeItem(UNLOCK_STORAGE_KEY);
  } catch {
    /* private mode — in-memory only */
  }
}

export function clearUnlockToken() {
  setUnlockToken(null);
}

/** Headers for any front-door call that may touch a locked resource. */
export function sdkUnlockHeaders(): Record<string, string> {
  const token = readToken();
  return token ? { 'X-Eclipse-Unlock': token } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = readToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { 'X-Eclipse-Unlock': token } : {}),
    ...((init.headers as Record<string, string> | undefined) ?? {}),
  };
  const res = await fetch(`/api/sdk${path}`, { ...init, headers });
  const data = (await res.json().catch(() => ({}))) as T & {
    error?: string;
    detail?: string | { code?: string; message?: string; lockId?: string; hint?: string };
  };
  if (!res.ok) {
    const detail = data.detail;
    const message = typeof detail === 'string'
      ? detail
      : detail?.message || data.error || `SDK request failed (${res.status})`;
    throw new SdkError(message, res.status, {
      code: typeof detail === 'object' ? detail?.code : undefined,
      lockId: typeof detail === 'object' ? detail?.lockId : undefined,
      hint: typeof detail === 'object' ? detail?.hint : undefined,
    });
  }
  return data;
}

function pageHref(page: string): string {
  const sp = new URLSearchParams({ tab: 'pages', page });
  return `/?${sp.toString()}`;
}

function notifyThemeChanged(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('eclipse:theme-changed'));
}

function afterThemeChange<T>(promise: Promise<T>): Promise<T> {
  return promise.then((result) => {
    notifyThemeChanged();
    return result;
  });
}

function notifyLocksChanged(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('eclipse:locks-changed'));
}

function afterLockChange<T>(promise: Promise<T>): Promise<T> {
  return promise.then((result) => {
    notifyLocksChanged();
    return result;
  });
}

/** Open a saved page through the shell's deep link (also works from the sidebar). */
export function openPage(pageIdOrPath: string) {
  if (typeof window === 'undefined') return;
  window.history.pushState(null, '', pageHref(pageIdOrPath));
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export const eclipseSdk = {
  capabilities() {
    return request<SdkCapabilities>('/capabilities');
  },

  app: {
    /** Read the app-wide nav order/visibility, active mode and the manifest. */
    get() {
      return request<AppShellResponse>('/app');
    },
    /** Reorder/hide/show sidebar sections and/or set the nav mode app-wide. */
    update(patch: AppNavPatch) {
      return request<AppShellResponse>('/app', {
        method: 'PUT',
        body: JSON.stringify({ nav: patch }),
      });
    },
    reset() {
      return request<AppShellResponse>('/app', { method: 'DELETE' });
    },
    /** Open a tab/page/dashboard in THIS shell immediately. */
    open(target: AppNavigateTarget) {
      navigateTo(target);
      return target;
    },
    /** Ask every connected shell (including chat/Python) to open a target. */
    navigate(target: AppNavigateTarget) {
      return request<{ success: boolean; target: AppNavigateTarget }>('/app/navigate', {
        method: 'POST',
        body: JSON.stringify({ target }),
      });
    },
  },

  audit: {
    list(filter: SdkAuditFilter = {}) {
      const qs = new URLSearchParams();
      for (const [key, value] of Object.entries(filter)) {
        if (value !== undefined && value !== '') qs.set(key, String(value));
      }
      const suffix = qs.toString();
      return request<{ entries: SdkAuditEntry[]; total: number }>(`/audit${suffix ? `?${suffix}` : ''}`);
    },
  },

  widgets: {
    list() {
      return request<{ widgets: SdkWidgetRecord[] }>('/widgets');
    },
    create(input: SdkWidgetInput) {
      return request<{ widget: SdkWidgetRecord }>('/widgets', { method: 'POST', body: JSON.stringify(input) });
    },
    remove(componentId: string) {
      return request<{ removed: boolean }>(`/widgets/${encodeURIComponent(componentId)}`, { method: 'DELETE' });
    },
  },

  pages: {
    list() {
      return request<{ blueprints: { id: string; title: string; path?: string | null; widgetCount: number }[]; total: number }>('/pages');
    },
    create(input: SdkCreatePageInput) {
      return request<{ blueprint: { id: string; title: string }; verification: unknown }>('/pages', {
        method: 'POST',
        body: JSON.stringify(input),
      });
    },
    update(blueprintId: string, patch: { title?: string; description?: string; path?: string; icon?: string; tags?: string[] }) {
      return request<{ blueprint: { id: string; title: string } }>(`/pages/${encodeURIComponent(blueprintId)}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
    },
    remove(blueprintId: string) {
      return request<{ removed: boolean }>(`/pages/${encodeURIComponent(blueprintId)}`, { method: 'DELETE' });
    },
    open: openPage,
  },

  dashboards: {
    list() {
      return request<{ dashboards: SdkDashboardSummary[]; activeDashboardId?: string | null }>('/dashboards');
    },
    active() {
      return request<SdkDashboardSnapshot>('/dashboards/active');
    },
    get(dashboardId: string) {
      return request<SdkDashboardSnapshot>(`/dashboards/${encodeURIComponent(dashboardId)}`);
    },
    setActive(dashboardId: string) {
      return request<{ activeDashboardId: string }>('/dashboards/active', {
        method: 'PUT',
        body: JSON.stringify({ dashboardId }),
      });
    },
    addWidget(dashboardId: string, input: SdkDashboardAddWidgetInput) {
      return request<SdkDashboardSnapshot>(`/dashboards/${encodeURIComponent(dashboardId)}/widgets`, {
        method: 'POST',
        body: JSON.stringify(input),
      });
    },
    removeWidget(dashboardId: string, instanceId: string, expectedRevision?: number) {
      const qs = expectedRevision === undefined ? '' : `?expectedRevision=${expectedRevision}`;
      return request<SdkDashboardSnapshot>(
        `/dashboards/${encodeURIComponent(dashboardId)}/widgets/${encodeURIComponent(instanceId)}${qs}`,
        { method: 'DELETE' },
      );
    },
    moveWidget(dashboardId: string, instanceId: string, target: SdkDashboardTarget, expectedRevision?: number) {
      return request<SdkDashboardSnapshot>(
        `/dashboards/${encodeURIComponent(dashboardId)}/widgets/${encodeURIComponent(instanceId)}/move`,
        { method: 'POST', body: JSON.stringify({ instanceId, target, expectedRevision }) },
      );
    },
    resizeWidget(dashboardId: string, instanceId: string, height: number | null, expectedRevision?: number) {
      return request<SdkDashboardSnapshot>(
        `/dashboards/${encodeURIComponent(dashboardId)}/widgets/${encodeURIComponent(instanceId)}/resize`,
        { method: 'POST', body: JSON.stringify({ instanceId, height, expectedRevision }) },
      );
    },
    setColumns(dashboardId: string, sectionId: string, count: number, expectedRevision?: number) {
      return request<SdkDashboardSnapshot>(`/dashboards/${encodeURIComponent(dashboardId)}/columns`, {
        method: 'PUT',
        body: JSON.stringify({ sectionId, count, expectedRevision }),
      });
    },
    setZones(dashboardId: string, input: { hiddenZones?: string[]; zoneWidths?: Record<string, number>; expectedRevision?: number }) {
      return request<SdkDashboardSnapshot>(`/dashboards/${encodeURIComponent(dashboardId)}/zones`, {
        method: 'PUT',
        body: JSON.stringify(input),
      });
    },
    setLayout(dashboardId: string, layout: SdkWorkspaceLayout, expectedRevision?: number) {
      return request<SdkDashboardSnapshot>(`/dashboards/${encodeURIComponent(dashboardId)}/layout`, {
        method: 'PUT',
        body: JSON.stringify({ layout, expectedRevision }),
      });
    },
    history(dashboardId: string) {
      return request<{ blueprintId: string; revisions: SdkDashboardRevision[] }>(`/dashboards/${encodeURIComponent(dashboardId)}/history`);
    },
    restore(dashboardId: string, revision: number) {
      return request<SdkDashboardSnapshot>(`/dashboards/${encodeURIComponent(dashboardId)}/restore`, {
        method: 'POST',
        body: JSON.stringify({ revision }),
      });
    },
    templates() {
      return request<{ templates: SdkDashboardTemplateSummary[] }>('/dashboards/templates');
    },
    /** Replace the board with a persona template (centre + side rails). */
    applyTemplate(dashboardId: string, templateId: string, options: { market?: string; expectedRevision?: number } = {}) {
      return request<SdkDashboardSnapshot>(`/dashboards/${encodeURIComponent(dashboardId)}/template`, {
        method: 'POST',
        body: JSON.stringify({ templateId, ...options }),
      });
    },
    /** Reset the board to the shipped default board/template. */
    reset(dashboardId: string, options: { market?: string; expectedRevision?: number } = {}) {
      return request<SdkDashboardSnapshot>(`/dashboards/${encodeURIComponent(dashboardId)}/reset`, {
        method: 'POST',
        body: JSON.stringify(options),
      });
    },
  },

  portfolio: {
    list() {
      return request<{ portfolios: SdkFund[] }>('/portfolios');
    },
    createFund(input: SdkCreateFundInput) {
      return request<{ fund: SdkFund }>('/funds', { method: 'POST', body: JSON.stringify(input) });
    },
    addStock(portfolioId: string, input: SdkAddStockInput) {
      return request<{ status: string; position?: unknown; warnings?: string[] }>(
        `/portfolios/${encodeURIComponent(portfolioId)}/stocks`,
        { method: 'POST', body: JSON.stringify(input) },
      );
    },
  },

  theme: {
    get() {
      return request<SdkThemeState>('/theme');
    },
    create(spec: ThemeSpec) {
      return afterThemeChange(request<{ theme: EclipseTheme; spec: ThemeSpec }>('/theme', {
        method: 'POST',
        body: JSON.stringify({ spec }),
      }));
    },
    apply(patch: ThemePatch) {
      return afterThemeChange(request<{ theme: EclipseTheme }>('/theme', {
        method: 'PUT',
        body: JSON.stringify({ patch }),
      }));
    },
    replace(theme: EclipseTheme) {
      return afterThemeChange(request<{ theme: EclipseTheme }>('/theme', {
        method: 'PUT',
        body: JSON.stringify({ theme }),
      }));
    },
    applyPreset(preset: string) {
      return afterThemeChange(request<{ theme: EclipseTheme; preset: unknown }>('/theme/presets/apply', {
        method: 'POST',
        body: JSON.stringify({ preset }),
      }));
    },
    listPresets() {
      return request<{ presets: SdkSavedThemePreset[] }>('/theme/presets');
    },
    savePreset(name: string, spec: ThemeSpec) {
      return request<{ preset: SdkSavedThemePreset }>('/theme/presets', {
        method: 'POST',
        body: JSON.stringify({ name, spec }),
      });
    },
    deletePreset(name: string) {
      return request<{ removed: boolean }>(`/theme/presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
    },
    reset() {
      return afterThemeChange(request<{ theme: EclipseTheme }>('/theme', { method: 'DELETE' }));
    },
  },

  design: {
    get() {
      return request<SdkDesignState>('/design');
    },
    apply(patch: ThemePatch) {
      return afterThemeChange(request<{ theme: EclipseTheme }>('/design', { method: 'PUT', body: JSON.stringify({ patch }) }));
    },
    replace(theme: EclipseTheme) {
      return afterThemeChange(request<{ theme: EclipseTheme }>('/design', { method: 'PUT', body: JSON.stringify({ theme }) }));
    },
    reset() {
      return afterThemeChange(request<{ theme: EclipseTheme }>('/design', { method: 'DELETE' }));
    },
  },

  locks: {
    list(filter: { resourceType?: string; resourceId?: string } = {}) {
      const qs = new URLSearchParams();
      for (const [key, value] of Object.entries(filter)) if (value) qs.set(key, value);
      return request<{ locks: SdkLock[] }>(`/locks?${qs.toString()}`);
    },
    create(input: SdkCreateLockInput) {
      return afterLockChange(
        request<{ lock: SdkLock }>('/locks', { method: 'POST', body: JSON.stringify(input) }),
      );
    },
    unlock(lockId: string, passphrase: string) {
      return request<{ token: string; expiresAt: string; lock: SdkLock }>(
        `/locks/${encodeURIComponent(lockId)}/unlock`,
        { method: 'POST', body: JSON.stringify({ passphrase }) },
      ).then((result) => {
        setUnlockToken(result.token);
        notifyLocksChanged();
        return result;
      });
    },
    remove(lockId: string, passphrase?: string) {
      const qs = passphrase ? `?passphrase=${encodeURIComponent(passphrase)}` : '';
      return afterLockChange(
        request<{ removed: boolean }>(`/locks/${encodeURIComponent(lockId)}${qs}`, { method: 'DELETE' }),
      );
    },
    assert(resourceType: SdkLock['resourceType'], resourceId: string, action: 'write' | 'delete' = 'write') {
      return request<{ locked: boolean }>('/locks/assert', {
        method: 'POST',
        body: JSON.stringify({ resourceType, resourceId, action }),
      });
    },
    clearUnlock: clearUnlockToken,
  },
};

export type EclipseSdk = typeof eclipseSdk;
