import { afterEach, describe, expect, it, vi } from 'vitest';
import { listVersions } from './persistence-client';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('workflow persistence client', () => {
  it('lists immutable versions through the versions route', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({
        versions: [{ version: 2, contentHash: 'abc', note: 'second', createdAt: '2026-10-25T00:00:00.000Z' }],
      }));
    const versions = await listVersions('wf_1');
    expect(versions).toHaveLength(1);
    expect(versions[0].version).toBe(2);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/workflows/wf_1/versions');
  });
});
