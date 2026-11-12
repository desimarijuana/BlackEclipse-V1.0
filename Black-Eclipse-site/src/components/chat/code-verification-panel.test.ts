import { describe, expect, it } from 'vitest';
import { claimStatusKey, coerceCodeVerification } from '@/lib/harness/clients/code-client';

// The invariant this phase exists to protect: an unsupported claim can NEVER be
// shown as verified. The panel chooses its status word through `claimStatusKey`,
// so the assertion belongs there (no React testing library is installed; the
// vitest include only matches `.test.ts`).

describe('code-verification panel logic', () => {
  it('never verifies an unsupported claim', () => {
    expect(claimStatusKey(false)).toBe('code.proof.notChecked');
    expect(claimStatusKey(true)).toBe('code.proof.verified');
  });

  it('coerces an empty/absent blob to null (no panel)', () => {
    expect(coerceCodeVerification(null)).toBeNull();
    expect(coerceCodeVerification({ records: [], claims: [], repair: null })).toBeNull();
  });

  it('keeps an unsupported claim unsupported through coercion', () => {
    const blob = {
      runId: 'r1',
      records: [],
      claims: [{ sentence: 'All tests pass.', kind: 'tests_pass', matchedClasses: ['unit_test'], supported: false }],
      unverifiedCount: 1,
      repair: null,
      truncated: false,
    };
    const coerced = coerceCodeVerification(blob);
    expect(coerced).not.toBeNull();
    expect(coerced!.claims[0].supported).toBe(false);
    expect(claimStatusKey(coerced!.claims[0].supported)).toBe('code.proof.notChecked');
  });
});
