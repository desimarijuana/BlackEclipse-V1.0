import { describe, it, expect } from 'vitest';
import { compareModelRecency, sortModelsNewestFirst } from './model-recency';

describe('model recency', () => {
  it('ranks a higher generation first within a family', () => {
    expect(sortModelsNewestFirst(['gpt-4o', 'gpt-5', 'gpt-4.1'])).toEqual([
      'gpt-5',
      'gpt-4.1',
      'gpt-4o',
    ]);
  });

  it('treats a dotted version as major.minor', () => {
    expect(sortModelsNewestFirst(['claude-sonnet-4-1', 'claude-sonnet-4-5'])).toEqual([
      'claude-sonnet-4-5',
      'claude-sonnet-4-1',
    ]);
  });

  it('prefers the -latest alias on a version tie', () => {
    expect(sortModelsNewestFirst(['claude-3-5-sonnet', 'claude-3-5-sonnet-latest'])).toEqual([
      'claude-3-5-sonnet-latest',
      'claude-3-5-sonnet',
    ]);
  });

  it('uses a provider created timestamp before the id heuristic', () => {
    const created = { 'gpt-4o': 1_700_000_000, 'gpt-5': 1_750_000_000 };
    expect(sortModelsNewestFirst(['gpt-4o', 'gpt-5'], created)).toEqual(['gpt-5', 'gpt-4o']);
    // An older id with a newer timestamp still wins.
    const flipped = { 'gpt-4o': 1_760_000_000, 'gpt-5': 1_750_000_000 };
    expect(sortModelsNewestFirst(['gpt-5', 'gpt-4o'], flipped)).toEqual(['gpt-4o', 'gpt-5']);
  });

  it('keeps the incoming order across different families', () => {
    const input = ['meta-llama/llama-3.3-70b', 'qwen/qwen2.5-vl-72b', 'anthropic/claude-sonnet-4.5'];
    expect(sortModelsNewestFirst(input)).toEqual(input);
    expect(compareModelRecency(input[0], input[1])).toBe(0);
  });

  it('leaves unknown custom ids in place', () => {
    const input = ['my-custom-model', 'another/thing'];
    expect(sortModelsNewestFirst(input)).toEqual(input);
  });
});
