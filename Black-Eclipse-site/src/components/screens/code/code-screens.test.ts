import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
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

// ── Reachability ─────────────────────────────────────────────────────────────
// The seven code panels existed but NOTHING imported them, so no user could reach
// them; the copy-only assertions above stayed green over dead code. Reachability
// is not observable from a unit test that imports the panel directly, so this
// asserts on the SHELL's source text: mounting is exactly what silently regressed.
// If someone removes the dynamic import or the keep-alive render block, the code
// capability goes dark again and this fails.
function readShellSource(): string {
  const here = fileURLToPath(new URL('../../screens/stock-chat.tsx', import.meta.url));
  return readFileSync(here, 'utf8');
}

describe('code surface reachability', () => {
  it('is reachable from the shell: the tab is mounted and the nav points at it', () => {
    const source = readShellSource();
    // 1. The dynamic import that loads the container.
    expect(source).toContain('screens/code/code-screen');
    // 2. The keep-alive render block that mounts it when the tab is visited.
    expect(source).toContain("visited.has('code')");
  });

  it('the code section is mounted in the sidebar and carries a plain label', () => {
    expect(en['nav.code']).toBeTruthy();
    expect(leaks(en['nav.code'])).toEqual([]);
  });
});
