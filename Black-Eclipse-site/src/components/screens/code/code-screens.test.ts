import { describe, expect, it } from 'vitest';
import { en } from '@/lib/i18n/dictionaries/en';

// The task surface presents the three autonomy choices as plain sentences and a
// task status as plain words. This asserts those keys exist and carry no
// mechanism word (the same denylist the jargon gate uses).

const DENYLIST = [
  'sandbox', 'worktree', 'workspace', 'allowlist', 'autonomy', 'digest',
  'argv', 'cwd', 'stderr', 'patch', 'diff', 'manifest', 'operator',
  'policy engine', 'tool registry', 'exit code', 'verification ledger',
];

function leaks(text: string): string[] {
  const lowered = text.toLowerCase();
  return DENYLIST.filter((word) =>
    new RegExp(`(^|[^a-z0-9])${word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`).test(lowered),
  );
}

const TASK_KEYS = [
  'code.task.autonomy.planOnly',
  'code.task.autonomy.editVerify',
  'code.task.autonomy.approveExternal',
  'code.task.status.created',
  'code.task.status.planReview',
  'code.task.status.completed',
  'code.task.status.failed',
  'code.task.status.cancelled',
  'code.task.status.discarded',
  'code.task.changeNewFile',
  'code.task.changeEditedFile',
  'code.task.changeRemovedFile',
] as const;

describe('code task screen copy', () => {
  it('has a plain sentence for every autonomy choice and status', () => {
    for (const key of TASK_KEYS) {
      expect(en[key], key).toBeTruthy();
    }
  });

  it('never names a mechanism in a task string', () => {
    const offenders: string[] = [];
    for (const key of TASK_KEYS) {
      const found = leaks(en[key]);
      if (found.length) offenders.push(`${key}: ${found.join(', ')}`);
    }
    expect(offenders).toEqual([]);
  });

  it('the three autonomy choices read as plain sentences', () => {
    expect(en['code.task.autonomy.planOnly']).toContain('Just tell me');
    expect(en['code.task.autonomy.editVerify']).toContain('Make the change');
    expect(en['code.task.autonomy.approveExternal']).toContain('ask me before');
  });
});
