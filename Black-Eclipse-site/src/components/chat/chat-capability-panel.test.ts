import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { en } from '@/lib/i18n/dictionaries/en';
import { coerceChatCapability, headlineKey } from '@/lib/harness/chat-capability-view';

// Phase 14 G4 — the chat capability panel.
//
// No React testing library is installed (the vitest include only matches
// `.test.ts`), so this asserts:
//   1. the panel is REACHABLE (imported by the chat surface — a copy-only test
//      over dead code stays green forever, as Phase 12.5 learned);
//   2. every string it renders is an i18n KEY that exists and carries no
//      mechanism word (the same denylist the jargon gate uses);
//   3. the profile → headline mapping is total and never shows a category.

const DENYLIST = [
  'sandbox', 'worktree', 'workspace', 'allowlist', 'autonomy', 'digest',
  'argv', 'cwd', 'stderr', 'stdout', 'patch', 'diff', 'manifest',
  'operator', 'policy engine', 'tool registry', 'exit code',
  'verification ledger', 'repo', 'repository', 'commit', 'branch', 'head',
];

function leaks(text: string): string[] {
  const lowered = text.toLowerCase();
  return DENYLIST.filter((word) =>
    new RegExp(`(^|[^a-z0-9])${word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`).test(lowered),
  );
}

const CHAT_KEYS = Object.keys(en).filter((key) => key.startsWith('code.chat.')) as Array<keyof typeof en>;

function surfaceSource(name: string): string {
  const here = fileURLToPath(new URL(`./${name}`, import.meta.url));
  return readFileSync(here, 'utf8');
}

describe('chat code capability panel', () => {
  it('maps each narrow profile to a plain headline key', () => {
    expect(headlineKey('edit_verify')).toBe('code.chat.headline.editVerify');
    expect(headlineKey('plan_only')).toBe('code.chat.headline.planOnly');
    // An ordinary turn, or an unknown value, shows no headline (never a category).
    expect(headlineKey(null)).toBeNull();
    expect(headlineKey(undefined)).toBeNull();
    expect(headlineKey('approve_external')).toBeNull();
  });

  it('has a plain sentence for every code.chat.* key', () => {
    expect(CHAT_KEYS.length).toBeGreaterThan(0);
    for (const key of CHAT_KEYS) {
      expect(en[key], key).toBeTruthy();
    }
  });

  it('never names a mechanism in a code.chat.* string', () => {
    const offenders: string[] = [];
    for (const key of CHAT_KEYS) {
      const found = leaks(en[key]);
      if (found.length) offenders.push(`${key}: ${found.join(', ')}`);
    }
    expect(offenders).toEqual([]);
  });

  it('is reachable: the chat surface imports the panel', () => {
    // The panel must be imported by the chat transcript so a coding turn renders
    // it — mounting is exactly what silently regresses.
    const history = surfaceSource('chat-history.tsx');
    expect(history).toContain('ChatCapabilityPanel');
    // And the named wiring point exists.
    const feed = surfaceSource('activity-feed.tsx');
    expect(feed).toContain('ChatCapabilityPanel');
    const row = surfaceSource('activity-item.tsx');
    expect(row).toContain('ChatCapabilityPanel');
  });

  it('composes the existing verification panel rather than re-rendering it', () => {
    const panel = surfaceSource('chat-capability-panel.tsx');
    expect(panel).toContain('CodeVerificationPanel');
  });

  it('coerces the runtime capability view, rejecting an ordinary or unknown one', () => {
    expect(coerceChatCapability(null)).toBeNull();
    expect(coerceChatCapability({})).toBeNull();
    expect(coerceChatCapability({ profile: 'approve_external' })).toBeNull();
    const view = coerceChatCapability({
      profile: 'edit_verify',
      headline: 'code.chat.headline.editVerify',
      verification: { records: [], claims: [] },
    });
    expect(view).not.toBeNull();
    expect(view!.profile).toBe('edit_verify');
    expect(view!.headline).toBe('code.chat.headline.editVerify');
  });
});
