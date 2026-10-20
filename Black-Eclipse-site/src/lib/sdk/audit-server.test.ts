import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  reachable: vi.fn(async () => true),
}));

vi.mock('@/lib/harness/python-runtime', () => ({
  HARNESS_PY_URL: 'http://127.0.0.1:9999',
  pythonRuntimeReachable: mocks.reachable,
}));
vi.mock('@/lib/harness/runtime-identity', () => ({
  runtimeProxyHeaders: vi.fn(async () => ({ 'X-Harness-Operator': 'test' })),
}));

import { recordSdkAudit } from './audit-server';

function request(): Request {
  return new Request('http://localhost/api/sdk/theme', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-eclipse-user': 'alice' },
  });
}

beforeEach(() => {
  mocks.reachable.mockResolvedValue(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('recordSdkAudit', () => {
  it('posts a front-door mutation to the runtime audit route', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await recordSdkAudit(request(), {
      action: 'theme.apply',
      summary: 'Updated the theme',
      resourceType: 'theme',
      resourceId: 'global',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('http://127.0.0.1:9999/sdk/audit');
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)['X-Harness-User']).toBe('alice');
    expect(JSON.parse(String(init.body)).action).toBe('theme.apply');
  });

  it('does not call the runtime when it is unreachable', async () => {
    mocks.reachable.mockResolvedValue(false);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await recordSdkAudit(request(), { action: 'theme.apply' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('never throws when the audit call fails', async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error('down');
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(recordSdkAudit(request(), { action: 'theme.apply' })).resolves.toBeUndefined();
  });
});
