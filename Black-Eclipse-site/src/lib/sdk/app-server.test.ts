import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defaultAppNav, type AppShellState } from './app-shell-types';

const mocks = vi.hoisted(() => {
  const state: AppShellState = {
    revision: 3,
    initialized: true,
    updatedAt: '2026-10-19T00:00:00.000Z',
    nav: { sections: [], mode: 'terminal' },
  };
  return {
    state,
    update: vi.fn(async (_patch: unknown) => ({ ...state, revision: 4, nav: defaultAppNav() })),
    reset: vi.fn(async () => ({ ...state, revision: 5, nav: defaultAppNav() })),
    publish: vi.fn(),
  };
});

vi.mock('./app-shell', () => ({
  getAppShellState: vi.fn(async () => mocks.state),
  updateAppShellNav: mocks.update,
  resetAppShellNav: mocks.reset,
  publishNavigation: mocks.publish,
  subscribeAppShell: vi.fn(() => () => undefined),
}));
vi.mock('./audit-server', () => ({ recordSdkAudit: vi.fn(async () => undefined) }));

import { appRoute } from './app-server';
import { recordSdkAudit } from './audit-server';

function request(method: string, body?: unknown): Request {
  return new Request('http://localhost/api/sdk/app', {
    method,
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

beforeEach(() => {
  mocks.state.nav = defaultAppNav();
  vi.clearAllMocks();
});

afterEach(() => vi.unstubAllGlobals());

describe('app shell routes', () => {
  it('returns the nav state plus the fixed manifest', async () => {
    const res = await appRoute(request('GET'), 'GET', ['app']);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.revision).toBe(3);
    expect(body.sections.map((section: { id: string }) => section.id)).toContain('dashboard');
    expect(body.modes).toContain('agentic');
  });

  it('persists a nav patch', async () => {
    const res = await appRoute(
      request('PUT', { nav: { mode: 'agentic', sections: [{ id: 'chat', enabled: false }] } }),
      'PUT',
      ['app'],
    );
    expect(res.status).toBe(200);
    expect(mocks.update).toHaveBeenCalledWith({
      mode: 'agentic',
      sections: [{ id: 'chat', enabled: false }],
    });
    const body = await res.json();
    expect(body.revision).toBe(4);
    expect(recordSdkAudit).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
      action: 'app.nav_update',
    }));
  });

  it('rejects an invalid mode, including inside the nav wrapper', async () => {
    const flat = await appRoute(request('PUT', { mode: 'everything' }), 'PUT', ['app']);
    expect(flat.status).toBe(400);
    const wrapped = await appRoute(request('PUT', { nav: { mode: 'everything' } }), 'PUT', ['app']);
    expect(wrapped.status).toBe(400);
    expect(mocks.update).not.toHaveBeenCalled();
  });

  it('publishes a navigation target', async () => {
    const res = await appRoute(
      request('POST', { target: { tab: 'dashboard', dashboardId: 'main' } }),
      'POST',
      ['app', 'navigate'],
    );
    expect(res.status).toBe(200);
    expect(mocks.publish).toHaveBeenCalledWith({ tab: 'dashboard', dashboardId: 'main' });
  });

  it('rejects an unknown tab', async () => {
    const res = await appRoute(
      request('POST', { target: { tab: 'not-a-tab' } }),
      'POST',
      ['app', 'navigate'],
    );
    expect(res.status).toBe(400);
    expect(mocks.publish).not.toHaveBeenCalled();
  });
});
