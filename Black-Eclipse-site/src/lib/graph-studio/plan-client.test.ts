import { afterEach, describe, expect, it, vi } from 'vitest';
import { planGraph } from './plan-client';

function mockFetch(body: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('chat-to-graph client', () => {
  it('parses a validated IR and its diagnostics', async () => {
    mockFetch({
      ok: true,
      ir: {
        irVersion: 1,
        id: 'wf_generated',
        name: 'Generated',
        description: '',
        meta: { createdAt: '', updatedAt: '', tags: ['generated'] },
        nodes: [{ id: 'trig', type: 'trigger.manual', version: '1.0.0', config: {}, layout: { x: 0, y: 0 } }],
        edges: [],
        settings: { executionMode: 'research', failFast: false, maxConcurrency: 4, timeoutMs: 0 },
        requiredCapabilities: [],
      },
      errors: [],
      warnings: ['w'],
      nodeCount: 1,
      executionMode: 'research',
      model: { provider: 'test', model: 'm' },
    });
    const result = await planGraph('build a scan');
    expect(result.ok).toBe(true);
    expect(result.ir?.name).toBe('Generated');
    expect(result.warnings).toEqual(['w']);
    expect(result.executionMode).toBe('research');
  });

  it('returns the validation errors without an IR', async () => {
    mockFetch({ ok: false, errors: [{ message: 'unknown node type' }], warnings: [] });
    const result = await planGraph('build a scan');
    expect(result.ok).toBe(false);
    expect(result.ir).toBeUndefined();
    expect(result.errors[0].message).toBe('unknown node type');
  });

  it('surfaces the runtime refusal message', async () => {
    mockFetch({ detail: 'no model provider is configured' }, 400);
    await expect(planGraph('build a scan')).rejects.toThrow('no model provider');
  });
});
