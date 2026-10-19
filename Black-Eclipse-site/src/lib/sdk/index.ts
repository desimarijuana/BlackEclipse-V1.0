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
}

export type SdkWidgetPrimitive =
  | 'data-table'
  | 'metric-card'
  | 'line-chart'
  | 'area-chart'
  | 'bar-chart'
  | 'pie-chart'
  | 'list'
  | 'markdown'
  | 'status-indicator'
  | 'empty-state'
  | 'error-state';

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
  resourceType: 'page' | 'widget' | 'portfolio' | 'design';
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

  design: {
    get() {
      return request<SdkDesignState>('/design');
    },
    apply(patch: ThemePatch) {
      return request<{ theme: EclipseTheme }>('/design', { method: 'PUT', body: JSON.stringify({ patch }) });
    },
    replace(theme: EclipseTheme) {
      return request<{ theme: EclipseTheme }>('/design', { method: 'PUT', body: JSON.stringify({ theme }) });
    },
    reset() {
      return request<{ theme: EclipseTheme }>('/design', { method: 'DELETE' });
    },
  },

  locks: {
    list(filter: { resourceType?: string; resourceId?: string } = {}) {
      const qs = new URLSearchParams();
      for (const [key, value] of Object.entries(filter)) if (value) qs.set(key, value);
      return request<{ locks: SdkLock[] }>(`/locks?${qs.toString()}`);
    },
    create(input: SdkCreateLockInput) {
      return request<{ lock: SdkLock }>('/locks', { method: 'POST', body: JSON.stringify(input) });
    },
    unlock(lockId: string, passphrase: string) {
      return request<{ token: string; expiresAt: string; lock: SdkLock }>(
        `/locks/${encodeURIComponent(lockId)}/unlock`,
        { method: 'POST', body: JSON.stringify({ passphrase }) },
      ).then((result) => {
        setUnlockToken(result.token);
        return result;
      });
    },
    remove(lockId: string, passphrase?: string) {
      const qs = passphrase ? `?passphrase=${encodeURIComponent(passphrase)}` : '';
      return request<{ removed: boolean }>(`/locks/${encodeURIComponent(lockId)}${qs}`, { method: 'DELETE' });
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
