import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { en } from '@/lib/i18n/dictionaries/en';
import { healthBucket, capabilityStateKey } from '@/lib/harness/model-runtime-browser';

// ── Model Control Center copy ────────────────────────────────────────────────
// The screen names the finance RESULT (which model answers a task), never the
// mechanism. Keys must exist and carry no plumbing word. The same denylist idea
// the jobs surface uses.

const DENYLIST = [
  'api key', 'provider adapter', 'allowlist', 'tool registry', 'routing score',
  'circuit breaker', 'token bucket', 'rate limit manager', 'fallback resolver',
  'schema validator', 'endpoint',
];

function leaks(text: string): string[] {
  const lowered = text.toLowerCase();
  return DENYLIST.filter((word) =>
    new RegExp(`(^|[^a-z0-9])${word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`).test(lowered),
  );
}

const KEYS = [
  'modelRuntime.title',
  'modelRuntime.description',
  'modelRuntime.tab.providers',
  'modelRuntime.tab.models',
  'modelRuntime.tab.routing',
  'modelRuntime.tab.usage',
  'modelRuntime.tab.health',
  'modelRuntime.tab.debug',
  'modelRuntime.col.provider',
  'modelRuntime.col.model',
  'modelRuntime.col.capabilities',
  'modelRuntime.col.pricing',
  'modelRuntime.col.health',
  'modelRuntime.usage.costUnknown',
  'modelRuntime.health.notMeasured',
  'modelRuntime.routing.aliasesHint',
  'modelRuntime.debug.selected',
  'modelRuntime.task.financial_research',
  'modelRuntime.capability.supported',
] as const;

describe('model runtime screen copy', () => {
  it('has a plain sentence for every control-center string', () => {
    for (const key of KEYS) {
      expect(en[key], key).toBeTruthy();
    }
  });

  it('no string names a mechanism', () => {
    const offenders: string[] = [];
    for (const key of KEYS) {
      const terms = leaks(en[key]);
      if (terms.length) offenders.push(`${key}: ${terms.join(', ')}`);
    }
    expect(offenders).toEqual([]);
  });

  it('every capability state resolves to a plain sentence', () => {
    for (const state of ['supported', 'unsupported', 'unknown', 'degraded'] as const) {
      const key = capabilityStateKey(state);
      expect(en[key as keyof typeof en], key).toBeTruthy();
    }
  });

  it('every task profile in the runtime catalog has a sentence', () => {
    const profiles = [
      'simple_chat', 'coding', 'code_review', 'financial_research',
      'financial_extraction', 'summarization', 'classification', 'planning',
      'agentic_execution', 'vision', 'document_analysis', 'background_task',
      'embedding', 'image_generation', 'audio', 'default',
    ];
    for (const p of profiles) {
      const key = `modelRuntime.task.${p}` as keyof typeof en;
      expect(en[key], key).toBeTruthy();
    }
  });
});

describe('render helpers', () => {
  it('healthBucket never fabricates a bucket for missing data', () => {
    expect(healthBucket(null)).toBe('unknown');
    expect(healthBucket(undefined)).toBe('unknown');
    expect(healthBucket(1)).toBe('good');
    expect(healthBucket(0.85)).toBe('watch');
    expect(healthBucket(0.5)).toBe('bad');
  });
});

// ── Reachability ─────────────────────────────────────────────────────────────
// The screen existed but nothing imported it would mean no user could inspect or
// route models. Asserting on the shell's source text is deliberate: mounting is
// not otherwise observable from a unit test, and it is what silently regresses.
function readShellSource(): string {
  const here = fileURLToPath(new URL('../../screens/stock-chat.tsx', import.meta.url));
  return readFileSync(here, 'utf8');
}

describe('model runtime surface reachability', () => {
  it('is reachable from the shell: the tab is mounted', () => {
    const source = readShellSource();
    expect(source).toContain('screens/model-runtime/model-runtime-screen');
    expect(source).toContain("visited.has('model-runtime')");
  });

  it('the nav points at it with a plain label', () => {
    expect(en['nav.modelRuntime']).toBeTruthy();
    expect(leaks(en['nav.modelRuntime'])).toEqual([]);
  });
});
