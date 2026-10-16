import { describe, expect, it, vi } from 'vitest';

// The route probes the runtime for a blueprint marker; stub it so the test
// never spawns Python.
vi.mock('@/lib/harness/python-runtime', () => ({
  HARNESS_PY_URL: 'http://127.0.0.1:0',
  ensurePythonRuntime: vi.fn(async () => false),
}));
vi.mock('@/lib/harness/runtime-auth', () => ({ runtimeCallbackToken: () => undefined }));

import { GET } from './route';

describe('GET /api/ui/stream', () => {
  it('opens an SSE stream and sends a connected frame', async () => {
    const controller = new AbortController();
    const res = await GET(new Request('http://localhost/api/ui/stream', { signal: controller.signal }));
    expect(res.headers.get('content-type')).toContain('text/event-stream');
    expect(res.headers.get('cache-control')).toContain('no-cache');
    expect(res.body).toBeTruthy();

    const reader = res.body!.getReader();
    const { value } = await reader.read();
    expect(new TextDecoder().decode(value)).toContain(': connected');
    await reader.cancel();
    controller.abort();
  });
});
