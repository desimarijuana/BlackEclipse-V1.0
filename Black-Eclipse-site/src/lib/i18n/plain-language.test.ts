import { describe, expect, it } from 'vitest';
import { en } from './dictionaries/en';
import { REFUSAL_KEY, refusalKey } from './refusal-copy';

// ── Plain-language (jargon) gate ─────────────────────────────────────────────
// Every phase that ships user-facing copy extends this gate. It fails when a
// user-visible string names a MECHANISM instead of the finance JOB. Phase 1's
// surface is the `task.*` and `refusal.*` keys plus the code→sentence map.
//
// The denylist is deliberately mechanism words only. It is matched
// case-insensitively on whole words / whole phrases, so "workspace" fails but a
// key name like `refusal.WORKSPACE_UNAVAILABLE` (a machine identifier, never
// shown) does not — the gate scans VALUES, not keys.

const PHASE_1_PREFIXES = [
  'task.navigator.', 'task.authoring.', 'task.check.',
  'code.proof.', 'code.task.', 'code.approvals.', 'refusal.',
  'analysis.', 'kit.', 'evolution.', 'jobs.', 'capability.',
];

const DENYLIST = [
  'sandbox',
  'worktree',
  'workspace',
  'allowlist',
  'autonomy',
  'digest',
  'argv',
  'cwd',
  'stderr',
  'stdout',
  'patch',
  'diff',
  'manifest',
  'operator',
  'policy engine',
  'tool registry',
  'sandbox backend',
  'exit code',
];

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function leaks(text: string): string[] {
  const found: string[] = [];
  for (const term of DENYLIST) {
    const pattern = new RegExp(`(^|[^a-z0-9])${escapeRegExp(term)}([^a-z0-9]|$)`, 'i');
    if (pattern.test(text)) found.push(term);
  }
  return found;
}

function phase1Entries(): Array<[string, string]> {
  return Object.entries(en).filter(([key]) =>
    PHASE_1_PREFIXES.some((prefix) => key.startsWith(prefix)),
  ) as Array<[string, string]>;
}

describe('plain-language gate — repository navigator strings', () => {
  it('adds the task/refusal keys this phase promised', () => {
    const entries = phase1Entries();
    expect(entries.length).toBeGreaterThan(0);
    const keys = entries.map(([key]) => key);
    expect(keys).toContain('task.navigator.title');
    expect(keys).toContain('refusal.PROTECTED_PATH');
  });

  it('no new user-facing value names a mechanism', () => {
    const offenders: string[] = [];
    for (const [key, value] of phase1Entries()) {
      const terms = leaks(value);
      if (terms.length) offenders.push(`${key}: ${terms.join(', ')}`);
    }
    expect(offenders).toEqual([]);
  });

  it('every refusal code resolves to a plain sentence', () => {
    const offenders: string[] = [];
    for (const code of Object.keys(REFUSAL_KEY)) {
      const key = refusalKey(code);
      const value = en[key];
      if (!value) {
        offenders.push(`${code} → missing key ${key}`);
        continue;
      }
      const terms = leaks(value);
      if (terms.length) offenders.push(`${code} → ${terms.join(', ')}`);
    }
    expect(offenders).toEqual([]);
  });

  it('an unknown code falls back to a real, plain sentence', () => {
    const key = refusalKey('SOMETHING_UNKNOWN');
    expect(en[key]).toBeTruthy();
    expect(leaks(en[key])).toEqual([]);
  });
});

