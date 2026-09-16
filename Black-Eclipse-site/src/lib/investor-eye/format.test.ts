import { describe, it, expect } from 'vitest';
import { formatEventTitle, formatUtc, formatPct } from './format';

describe('formatEventTitle', () => {
  it('restructures two synthesized actors into a sentence', () => {
    expect(formatEventTitle('IRANIAN / IRAN — Shandong, Jiangsu, China'))
      .toBe('IRANIAN and IRAN in Shandong, Jiangsu, China');
  });

  it('restructures a single actor', () => {
    expect(formatEventTitle('POLICE — Washington, District of Columbia, United States'))
      .toBe('POLICE in Washington, District of Columbia, United States');
  });

  it('joins three actors with commas and a final "and"', () => {
    expect(formatEventTitle('PRISON / PHILADELPHIA / UNITED STATES'))
      .toBe('PRISON, PHILADELPHIA and UNITED STATES');
  });

  it('uses the structured place when the title has no geo tail', () => {
    expect(formatEventTitle('POLICE', 'Manila, Philippines')).toBe('POLICE in Manila, Philippines');
  });

  it('leaves a plain actor-only title alone when there is no place', () => {
    expect(formatEventTitle('POLICE')).toBe('POLICE');
  });

  it('returns a real headline untouched', () => {
    const headline = 'Port workers strike over pay in Rotterdam';
    expect(formatEventTitle(headline)).toBe(headline);
  });

  it('does not rewrite a headline that merely contains a slash', () => {
    const h = 'GDP/CPI divergence widens across the euro area this quarter';
    expect(formatEventTitle(h)).toBe(h);
  });

  it('handles empty and whitespace input', () => {
    expect(formatEventTitle('')).toBe('');
    expect(formatEventTitle('   ')).toBe('');
  });

  it('handles an en-dash as well as an em-dash', () => {
    expect(formatEventTitle('BOLIVIA – Colchani, La Paz, Bolivia'))
      .toBe('BOLIVIA in Colchani, La Paz, Bolivia');
  });
});

describe('formatUtc / formatPct', () => {
  it('formats UTC and percentages', () => {
    expect(formatUtc('2026-09-16T21:30:00.000Z')).toBe('21:30 UTC');
    expect(formatUtc(null)).toBe('—');
    expect(formatPct(1.234)).toBe('+1.23%');
    expect(formatPct(-0.5)).toBe('-0.50%');
    expect(formatPct(undefined)).toBe('—');
  });
});
