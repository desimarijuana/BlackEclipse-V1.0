import { describe, expect, it } from 'vitest';
import { FINANCE_GROUP_NAME, financeBotPack } from './finance-bots';

describe('finance starter pack', () => {
  it('defines six uniquely named bots', () => {
    const pack = financeBotPack();
    expect(pack).toHaveLength(6);
    expect(new Set(pack.map((b) => b.name)).size).toBe(6);
  });

  it('every spec is non-empty and has real instructions', () => {
    for (const spec of financeBotPack()) {
      expect(spec.name.trim()).not.toBe('');
      expect(spec.description.trim()).not.toBe('');
      expect(spec.objective.trim().length).toBeGreaterThan(40);
      expect(spec.agentId.trim()).not.toBe('');
    }
  });

  it('cron triggers use a five-field expression', () => {
    for (const spec of financeBotPack()) {
      if (spec.trigger.type === 'cron') {
        expect(spec.trigger.cron?.trim().split(/\s+/)).toHaveLength(5);
      }
    }
  });

  it('names the group room that holds the whole pack', () => {
    expect(FINANCE_GROUP_NAME).toBe('Markets Desk');
    expect(financeBotPack()).toHaveLength(6);
  });
});
