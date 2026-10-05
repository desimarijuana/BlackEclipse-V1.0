import { describe, expect, it, vi, afterEach } from 'vitest';
import { capabilityStateKey, healthBucket, pricingKey, discoverRuntimeModels } from '@/lib/harness/model-runtime-browser';

// The Model Runtime browser client must be CLIENT-SAFE: importing the server
// client (model-runtime-client.ts) pulls `ensurePythonRuntime` → `child_process`
// into the browser bundle. This mirrors the jobs split guard. We assert the
// browser module's source has no server-only import.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

describe('model runtime browser client', () => {
  it('does not import server-only runtime code', () => {
    const here = fileURLToPath(new URL('./model-runtime-browser.ts', import.meta.url));
    const source = readFileSync(here, 'utf8');
    const importLines = source
      .split('\n')
      .filter((line) => /^\s*(import|export)\b/.test(line));
    const serverImports = importLines.filter((line) => /python-runtime|runtime-auth|child_process/.test(line));
    expect(serverImports).toEqual([]);
  });

  it('maps capability states to plain keys', () => {
    expect(capabilityStateKey('supported')).toBe('modelRuntime.capability.supported');
    expect(capabilityStateKey('degraded')).toBe('modelRuntime.capability.degraded');
  });

  it('pricing keys never claim a number for unknown', () => {
    expect(pricingKey('unknown')).toBe('modelRuntime.pricing.unknown');
    expect(pricingKey('free')).toBe('modelRuntime.pricing.free');
  });

  it('healthBucket treats absent evidence as unknown, never zero', () => {
    expect(healthBucket(null)).toBe('unknown');
  });

  describe('discoverRuntimeModels', () => {
    afterEach(() => vi.unstubAllGlobals());

    it('posts connection details to the provider discover route and normalizes the result', async () => {
      const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
        ok: true,
        json: async () => ({
          success: true,
          ok: true,
          detail: null,
          models: [{ id: 'llama3.2' }],
          served: ['llama3.2'],
        }),
      }));
      vi.stubGlobal('fetch', fetchMock);
      const res = await discoverRuntimeModels('ollama', { baseUrl: 'http://localhost:11434/v1' });
      expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/harness/model-runtime/providers/ollama/discover');
      expect(res.ok).toBe(true);
      expect(res.models[0]?.id).toBe('llama3.2');
      expect(res.served).toEqual(['llama3.2']);
    });

    it('normalizes a missing served list to an empty array', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => ({
          ok: true,
          json: async () => ({ success: true, ok: true, detail: null, models: [{ id: 'x' }] }),
        })),
      );
      const res = await discoverRuntimeModels('ollama', { baseUrl: 'http://localhost:11434/v1' });
      expect(res.served).toEqual([]);
    });

    it('surfaces an honest failure instead of a silent empty success', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => ({
          ok: true,
          json: async () => ({ success: true, ok: false, detail: 'connection refused', models: [] }),
        })),
      );
      const res = await discoverRuntimeModels('ollama', { baseUrl: 'http://localhost:9/v1' });
      expect(res.ok).toBe(false);
      expect(res.detail).toBe('connection refused');
      expect(res.models).toEqual([]);
    });
  });
});
