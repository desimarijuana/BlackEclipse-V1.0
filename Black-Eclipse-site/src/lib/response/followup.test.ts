import { describe, expect, it } from 'vitest';
import {
  composeFollowupPrompt,
  formatFollowupValue,
  labelsById,
  renderFollowupTemplate,
} from './followup';

describe('followup state → prompt', () => {
  it('formats scalars, booleans and date ranges', () => {
    expect(formatFollowupValue('x')).toBe('x');
    expect(formatFollowupValue(5)).toBe('5');
    expect(formatFollowupValue(true)).toBe('on');
    expect(formatFollowupValue({ from: '2025-01-01', to: '' })).toBe('2025-01-01..?');
    expect(formatFollowupValue(undefined)).toBe('');
  });

  it('interpolates placeholders and date fields, missing keys become empty', () => {
    const out = renderFollowupTemplate(
      'Screen {{pe}} in {{window.from}}..{{window.to}} ({{missing}})',
      { pe: 20, window: { from: '2025-01-01', to: '2025-06-30' } },
    );
    expect(out).toBe('Screen 20 in 2025-01-01..2025-06-30 ()');
  });

  it('composes the default Label: value form in the given order', () => {
    const out = composeFollowupPrompt({
      state: { b: 2, a: 1 },
      order: ['a', 'b'],
      labels: { a: 'Alpha', b: 'Beta' },
      lead: 'Run it',
    });
    expect(out).toBe('Run it — Alpha: 1; Beta: 2');
  });

  it('falls back to the block id and fallback lead', () => {
    const out = composeFollowupPrompt({ state: { pe: 12 } });
    expect(out).toBe('Continue with these parameters — pe: 12');
  });

  it('a template wins over the default form', () => {
    const out = composeFollowupPrompt({
      state: { pe: 12, sector: 'tech' },
      template: 'Re-run with max P/E {{pe}} and sector {{sector}}.',
      lead: 'ignored',
    });
    expect(out).toBe('Re-run with max P/E 12 and sector tech.');
  });

  it('builds labels by id', () => {
    expect(labelsById([{ id: 'a', label: 'Alpha' }])).toEqual({ a: 'Alpha' });
  });
});
