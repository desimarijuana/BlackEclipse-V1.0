import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/harness/python-runtime', () => ({
  HARNESS_PY_URL: 'http://127.0.0.1:9999',
  ensurePythonRuntime: vi.fn(async () => true),
}));
vi.mock('@/lib/harness/runtime-identity', () => ({
  runtimeProxyHeaders: vi.fn(async () => ({ 'X-Harness-Operator': 'test' })),
}));
vi.mock('./audit-server', () => ({ recordSdkAudit: vi.fn(async () => undefined) }));

import { dashboardRoute } from './dashboard-server';
import { recordSdkAudit } from './audit-server';

function request(method: string, body?: unknown): Request {
  return new Request('http://localhost/api/sdk/dashboards/main/template', {
    method,
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('dashboard template routes', () => {
  it('lists the TypeScript persona templates', async () => {
    const res = await dashboardRoute(request('GET'), 'GET', ['dashboards', 'templates']);
    expect(res?.status).toBe(200);
    const body = await res!.json();
    expect(body.templates.map((template: { id: string }) => template.id)).toContain('rates-desk');
  });

  it('builds and writes a template with the current revision', async () => {
    const puts: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (url: string | URL, init?: RequestInit) => {
      const target = String(url);
      if (target.endsWith('/sdk/dashboards/main') && (!init || init.method === undefined || init.method === 'GET')) {
        return jsonResponse({ dashboard: { dashboardId: 'main' }, revision: 7 });
      }
      if (target.endsWith('/sdk/dashboards/main/layout') && init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return jsonResponse({ dashboard: { dashboardId: 'main', revision: 8 }, revision: 8 });
      }
      return jsonResponse({ error: 'unexpected' }, 500);
    });
    vi.stubGlobal('fetch', fetchMock);

    const res = await dashboardRoute(
      request('POST', { templateId: 'rates-desk', market: 'US' }),
      'POST',
      ['dashboards', 'main', 'template'],
    );
    expect(res?.status).toBe(200);
    expect(puts).toHaveLength(1);
    expect(puts[0].expectedRevision).toBe(7);
    const layout = puts[0].layout as { sections: unknown[] };
    expect(layout.sections.length).toBeGreaterThan(0);
    const body = await res!.json();
    expect(body.revision).toBe(8);
    expect(recordSdkAudit).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
      action: 'dashboard.apply_template',
      resourceId: 'main',
    }));
  });

  it('rejects an unknown template without writing', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ dashboard: { dashboardId: 'main' }, revision: 7 }));
    vi.stubGlobal('fetch', fetchMock);
    const res = await dashboardRoute(
      request('POST', { templateId: 'not-real' }),
      'POST',
      ['dashboards', 'main', 'template'],
    );
    expect(res?.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('ignores non-template dashboard paths', async () => {
    expect(await dashboardRoute(request('GET'), 'GET', ['dashboards', 'main'])).toBeNull();
  });
});
