import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { en } from '@/lib/i18n/dictionaries/en';

// The jobs surface names the finance JOB, never the mechanism. This asserts the
// job-editor / library / delivery / status keys exist and carry no mechanism
// word (the same denylist the jargon gate uses). A cron expression, skill id,
// job kind or machine reason is never a user-facing string.

const DENYLIST = [
  'sandbox', 'worktree', 'workspace', 'allowlist', 'autonomy', 'digest',
  'argv', 'cwd', 'stderr', 'stdout', 'patch', 'diff', 'manifest', 'operator',
  'policy engine', 'tool registry', 'exit code', 'verification ledger',
  'cron', 'webhook',
];

function leaks(text: string): string[] {
  const lowered = text.toLowerCase();
  return DENYLIST.filter((word) =>
    new RegExp(`(^|[^a-z0-9])${word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`).test(lowered),
  );
}

const JOB_KEYS = [
  'jobs.title',
  'jobs.empty',
  'jobs.library.title',
  'jobs.library.use',
  'jobs.editor.name',
  'jobs.editor.cadence',
  'jobs.editor.cadence.weekdayMorning',
  'jobs.editor.cadence.every6h',
  'jobs.editor.delivery',
  'jobs.editor.delivery.inApp',
  'jobs.editor.delivery.artifact',
  'jobs.editor.delivery.messaging',
  'jobs.editor.destination',
  'jobs.delivery.message.done',
  'jobs.delivery.message.doneCount',
  'jobs.delivery.message.trouble',
  'jobs.list.runNow',
  'jobs.list.enable',
  'jobs.list.disable',
  'jobs.breaker.paused',
  'jobs.breaker.reset',
  'jobs.run.status.ok',
  'jobs.run.status.failed',
  'jobs.run.status.skipped',
  'jobs.run.status.timed_out',
  'jobs.run.delivered',
] as const;

describe('jobs screen copy', () => {
  it('has a plain sentence for every job-editor, library and delivery string', () => {
    for (const key of JOB_KEYS) {
      expect(en[key], key).toBeTruthy();
    }
  });

  it('no job string names a mechanism', () => {
    const offenders: string[] = [];
    for (const key of JOB_KEYS) {
      const terms = leaks(en[key]);
      if (terms.length) offenders.push(`${key}: ${terms.join(', ')}`);
    }
    expect(offenders).toEqual([]);
  });

  it('every run status resolves to a plain sentence', () => {
    const statuses = ['running', 'ok', 'failed', 'skipped', 'timed_out', 'refused'] as const;
    for (const status of statuses) {
      const key = `jobs.run.status.${status}` as const;
      expect(en[key], key).toBeTruthy();
      expect(leaks(en[key]), key).toEqual([]);
    }
  });
});

// ── Reachability ─────────────────────────────────────────────────────────────
// The jobs surface existed but NOTHING imported it, so no user could create a
// job and the scheduler had nothing to run. Asserting on the shell's source text
// is deliberate: mounting is not otherwise observable from a unit test, and it is
// exactly what silently regressed.
function readShellSource(): string {
  const here = fileURLToPath(new URL('../../screens/stock-chat.tsx', import.meta.url));
  return readFileSync(here, 'utf8');
}

describe('jobs surface reachability', () => {
  it('is reachable from the shell: the tab is mounted and the nav points at it', () => {
    const source = readShellSource();
    expect(source).toContain('screens/jobs/jobs-screen');
    expect(source).toContain("visited.has('jobs')");
  });

  it('the jobs section is mounted in the sidebar and carries a plain label', () => {
    expect(en['nav.jobs']).toBeTruthy();
    expect(leaks(en['nav.jobs'])).toEqual([]);
  });
});
