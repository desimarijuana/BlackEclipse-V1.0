import { describe, expect, it } from 'vitest';
import { capabilityStateKey, healthBucket, pricingKey } from '@/lib/harness/model-runtime-browser';

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
});
