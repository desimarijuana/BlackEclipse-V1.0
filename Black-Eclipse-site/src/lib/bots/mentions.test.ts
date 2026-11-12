import { describe, expect, it } from 'vitest';
import type { AutomationView } from '@/lib/harness/clients/automation-client';
import type { BotGroup } from '@/lib/bots/groups-store';
import {
  buildMentionTargets,
  mentionedTargets,
  parseMentions,
  searchMentions,
  type MentionTarget,
} from './mentions';

function bot(id: string, name: string, description: string | null = null, objective: string | null = null): AutomationView {
  return {
    id,
    name,
    description,
    action: { objective },
  } as unknown as AutomationView;
}

function group(id: string, name: string, memberIds: string[]): BotGroup {
  return { id, name, memberIds, createdAt: '2026-01-01T00:00:00.000Z' };
}

const BOT = (id: string, name: string): MentionTarget => ({
  kind: 'bot', id, name, description: '', memberIds: [],
});

describe('buildMentionTargets', () => {
  it('projects bots and groups, skipping unnamed records', () => {
    const targets = buildMentionTargets(
      [bot('b1', 'Portfolio Bot', 'Watches my risk'), bot('b2', '   ')],
      [group('g1', 'Morning Desk', ['b1', 'b3'])],
    );
    expect(targets).toEqual([
      { kind: 'bot', id: 'b1', name: 'Portfolio Bot', description: 'Watches my risk', memberIds: [] },
      { kind: 'group', id: 'g1', name: 'Morning Desk', description: '2 members', memberIds: ['b1', 'b3'] },
    ]);
  });

  it('falls back to the objective when there is no description', () => {
    const [target] = buildMentionTargets([bot('b1', 'Bot', null, 'Watch the tape')], []);
    expect(target.description).toBe('Watch the tape');
  });
});

describe('searchMentions', () => {
  const targets = [BOT('b1', 'Portfolio'), BOT('b2', 'Portfolio Bot'), BOT('b3', 'Momentum')];

  it('ranks an exact name first', () => {
    expect(searchMentions(targets, 'portfolio')[0].id).toBe('b1');
  });

  it('ranks a prefix match above a later substring', () => {
    const ids = searchMentions(targets, 'port').map((t) => t.id);
    expect(ids).toContain('b1');
    expect(ids).toContain('b2');
  });

  it('is deterministic and capped when the query is empty', () => {
    const first = searchMentions(targets, '').map((t) => t.id);
    const second = searchMentions(targets, '').map((t) => t.id);
    expect(first).toEqual(second);
    expect(first).toEqual(['b3', 'b1', 'b2']); // alphabetical by name
    expect(searchMentions(targets, '', 2)).toHaveLength(2);
  });
});

describe('parseMentions', () => {
  const targets = [BOT('b1', 'Portfolio'), BOT('b2', 'Portfolio Bot'), BOT('b3', 'Bob')];

  it('resolves a simple mention', () => {
    const [m] = parseMentions('@Momentum check this', [BOT('b9', 'Momentum')]);
    expect(m.target.id).toBe('b9');
    expect(m.start).toBe(0);
    expect(m.end).toBe('@Momentum'.length);
  });

  it('is case-insensitive and matches mid-text after whitespace', () => {
    const [m] = parseMentions('hey @bob look', targets);
    expect(m.target.id).toBe('b3');
  });

  it('prefers the longest name (multi-word beats prefix)', () => {
    const [m] = parseMentions('@Portfolio Bot do it', targets);
    expect(m.target.id).toBe('b2');
  });

  it('does not match a name embedded in a longer word', () => {
    expect(parseMentions('@Bobby hello', targets)).toEqual([]);
  });

  it('never matches an email or a mid-word @', () => {
    expect(parseMentions('mail me at a@bob.com', targets)).toEqual([]);
  });

  it('collapses duplicate mentions to the first occurrence', () => {
    const found = parseMentions('@Bob and @bob again', targets);
    expect(found).toHaveLength(1);
  });

  it('resolves every target that shares the longest name', () => {
    const same = [BOT('b1', 'Desk'), BOT('b2', 'Desk'), BOT('b3', 'Desk Bot')];
    expect(parseMentions('@Desk run it', same).map((m) => m.target.id)).toEqual(['b1', 'b2']);
    expect(parseMentions('@Desk Bot run it', same).map((m) => m.target.id)).toEqual(['b3']);
  });

  it('returns nothing without targets', () => {
    expect(parseMentions('@Anything', [])).toEqual([]);
  });
});

describe('mentionedTargets', () => {
  it('returns distinct targets in first-appearance order', () => {
    const targets = [BOT('b1', 'Alpha'), BOT('b2', 'Beta'), BOT('b3', 'Gamma')];
    const got = mentionedTargets('@Beta then @Alpha then @Beta', targets).map((t) => t.id);
    expect(got).toEqual(['b2', 'b1']);
  });
});
