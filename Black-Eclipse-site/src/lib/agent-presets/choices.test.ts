import { describe, expect, it } from 'vitest';
import { mergeAgentChoices } from './choices';
import type { AgentPresetSummary } from './client';

function preset(overrides: Partial<AgentPresetSummary> = {}): AgentPresetSummary {
  return {
    id: 'gold-analyst',
    name: 'Gold analyst',
    description: 'Intraday gold reader',
    version: 2,
    maxSteps: 6,
    toolCount: 2,
    effects: [],
    archived: false,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-02T00:00:00Z',
    ...overrides,
  };
}

const builtins = [
  { id: 'eclipse-agent', name: 'Eclipse Agent' },
  { id: 'code-agent', name: 'Code Agent' },
];

describe('mergeAgentChoices', () => {
  it('puts built-ins first, then presets by name', () => {
    const choices = mergeAgentChoices({
      builtins,
      presets: [preset({ id: 'zeta', name: 'Zeta desk' }), preset({ id: 'alpha', name: 'Alpha desk' })],
    });
    expect(choices.map((choice) => choice.id)).toEqual(['eclipse-agent', 'code-agent', 'alpha', 'zeta']);
    expect(choices[0]).toMatchObject({ source: 'builtin', label: 'Eclipse Agent' });
    expect(choices[2]).toMatchObject({ source: 'preset', version: 2 });
  });

  it('never offers the same id twice (a preset cannot shadow a built-in)', () => {
    const choices = mergeAgentChoices({
      builtins,
      presets: [preset({ id: 'code-agent', name: 'Impostor' })],
    });
    expect(choices.map((choice) => choice.id)).toEqual(['eclipse-agent', 'code-agent']);
    expect(choices[1].label).toBe('Code Agent');
  });

  it('keeps an archived preset selectable so an edit cannot retarget the bot', () => {
    const choices = mergeAgentChoices({
      builtins,
      presets: [preset({ archived: true })],
      currentId: 'gold-analyst',
    });
    expect(choices.find((choice) => choice.id === 'gold-analyst')).toMatchObject({
      source: 'preset',
      archived: true,
    });
    expect(choices).toHaveLength(3);
  });

  it('appends a saved value the runtime does not know, labelled honestly', () => {
    const choices = mergeAgentChoices({ builtins, presets: [], currentId: 'deleted-preset' });
    expect(choices.at(-1)).toEqual({
      id: 'deleted-preset',
      label: 'deleted-preset (not found)',
      description: 'This agent no longer exists. Pick another one before saving.',
      source: 'unknown',
    });
  });

  it('does not append a current value that is already offered', () => {
    const choices = mergeAgentChoices({ builtins, presets: [], currentId: 'eclipse-agent' });
    expect(choices.filter((choice) => choice.source === 'unknown')).toHaveLength(0);
    expect(choices).toHaveLength(2);
  });

  it('ignores blank ids', () => {
    const choices = mergeAgentChoices({
      builtins: [{ id: '  ', name: 'Blank' }, ...builtins],
      presets: [preset({ id: '   ' })],
      currentId: '   ',
    });
    expect(choices.map((choice) => choice.id)).toEqual(['eclipse-agent', 'code-agent']);
  });
});
