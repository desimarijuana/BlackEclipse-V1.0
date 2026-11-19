import { describe, expect, it } from 'vitest';
import {
  DESK_TAG,
  deskCreateInput,
  deskDraftFromAutomation,
  deskIssues,
  deskTeamOf,
  deskToTeam,
  duplicateDeskConfig,
  emptyDeskDraft,
  newDeskStage,
  nextStageKey,
  resolveObjective,
} from './desk';

const named = () => {
  const draft = emptyDeskDraft();
  draft.name = 'Rates desk';
  draft.objective = 'Should we add duration here?';
  return draft;
};

describe('desk draft → team definition', () => {
  it('maps the starter to a reviewable graph that mirrors the builder', () => {
    const draft = named();
    const team = deskToTeam(draft);

    expect(team.id).toBe(draft.id);
    expect(team.members).toHaveLength(3);
    expect(team.subtasks.map((s) => s.id)).toEqual(['research', 'challenge', 'decision']);
    expect(team.subtasks[2].dependsOn).toEqual(['research', 'challenge']);
    expect(team.policy?.requireReview).toBe(true);
    expect(team.policy?.reviewStrictness).toBe('STRICT');
    expect(team.policy?.optionalFailurePolicy).toBe('REQUIRE_ALL');
  });

  it('gives every stage its own runtime agent so two desks never collide', () => {
    const first = deskToTeam(named());
    const secondDraft = named();
    secondDraft.id = 'desk_other';
    const second = deskToTeam(secondDraft);

    const ids = [...first.members, ...second.members].map((m) => m.agentId);
    expect(new Set(ids).size).toBe(ids.length);
    expect(first.members[0].agentId.startsWith(first.id)).toBe(true);
  });

  it('substitutes the desk question into a stage objective', () => {
    const draft = named();
    const team = deskToTeam(draft);
    expect(team.subtasks[0].objective).toContain('Should we add duration here?');
    expect(resolveObjective('Do {{ objective }} now', 'X')).toBe('Do X now');
  });

  it('creates a run_team bot tagged for Bots mode', () => {
    const input = deskCreateInput(named());
    expect(input.action.type).toBe('run_team');
    expect(input.tags).toEqual(['bot', DESK_TAG]);
    expect(input.trigger.type).toBe('manual');
    const team = input.action.config?.team as { subtasks: unknown[] };
    expect(team.subtasks).toHaveLength(3);
  });

  it('wires a monitor completion to the desk and carries its memo as a lead', () => {
    const draft = named();
    draft.trigger = { kind: 'event', intervalMinutes: 15, sourceBotId: 'bot_news' };
    const input = deskCreateInput(draft);

    expect(input.trigger).toMatchObject({
      type: 'event',
      eventType: 'automation.completed',
      eventFilter: { automationId: 'bot_news' },
    });
    expect(input.action.config?.contextAutomationId).toBe('bot_news');
  });

  it('turns an interval desk into real seconds', () => {
    const draft = named();
    draft.trigger = { kind: 'interval', intervalMinutes: 15, sourceBotId: '' };
    expect(deskCreateInput(draft).trigger).toMatchObject({
      type: 'interval',
      intervalSeconds: 900,
    });
  });
});

describe('desk draft validation', () => {
  it('accepts the starter once named', () => {
    expect(deskIssues(named())).toEqual([]);
  });

  it('explains the common mistakes', () => {
    const draft = named();
    draft.name = '';
    draft.stages = [newDeskStage('research', 'research')];
    draft.stages[0].tools = [...draft.stages[0].tools, 'order_submit'];
    draft.stages[0].dependsOn = ['ghost'];

    const issues = deskIssues(draft).join(' ');
    expect(issues).toContain('name');
    expect(issues).toContain('at least two stages');
    expect(issues).toContain('unknown stage "ghost"');
    expect(issues).toContain('not submit an order');
  });

  it('never reuses a stage id', () => {
    const draft = named();
    expect(nextStageKey(draft, 'research')).toBe('research-2');
  });
});

describe('desk hydration', () => {
  it('round-trips a saved desk back into the builder', () => {
    const draft = named();
    const bot = {
      action: deskCreateInput(draft).action,
      trigger: { type: 'manual', eventFilter: {}, intervalSeconds: null },
    } as never;
    const team = deskTeamOf(bot);
    expect(team).not.toBeNull();

    const back = deskDraftFromAutomation(bot);
    expect(back.id).toBe(draft.id);
    expect(back.objective).toBe(draft.objective);
    expect(back.stages.map((s) => s.key)).toEqual(['research', 'challenge', 'decision']);
    expect(back.stages[0].label).toBe('Research');
    expect(back.trigger.kind).toBe('manual');
  });

  it('returns an empty draft for a bot that is not a desk', () => {
    const back = deskDraftFromAutomation({
      action: { type: 'run_agent', config: {} },
      trigger: { type: 'manual', eventFilter: {} },
    } as never);
    expect(back.stages.length).toBeGreaterThan(1);
  });

  it('gives a duplicated desk fresh ids so it never reuses the original agents', () => {
    const draft = named();
    const original = deskToTeam(draft);
    const bot = {
      action: deskCreateInput(draft).action,
      trigger: { type: 'manual', eventFilter: {} },
    } as never;

    const config = duplicateDeskConfig(bot);
    expect(config).not.toBeNull();
    expect(config?.teamId).not.toBe(original.id);
    const team = config?.team as { members: Array<{ agentId: string }>; subtasks: Array<{ assignedAgentId: string }> };
    const originalIds = new Set(original.members.map((m) => m.agentId));
    for (const member of team.members) {
      expect(originalIds.has(member.agentId)).toBe(false);
      expect(member.agentId.startsWith(String(config?.teamId))).toBe(true);
    }
    for (const subtask of team.subtasks) {
      expect(team.members.some((m) => m.agentId === subtask.assignedAgentId)).toBe(true);
    }
  });
});
