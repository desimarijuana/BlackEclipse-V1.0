import { describe, it, expect } from 'vitest';
import { parseFinancialFacts, parseNumber } from './research-parse';

describe('parseNumber', () => {
  it('parses scaled words', () => {
    expect(parseNumber('1.2 billion')?.value).toBe(1.2e9);
    expect(parseNumber('Revenue was 500 million USD')?.value).toBe(5e8);
  });
  it('parses suffixes and commas', () => {
    expect(parseNumber('$1,234.5M')?.value).toBe(1234.5e6);
    expect(parseNumber('12.3%')?.value).toBe(12.3);
  });
  it('returns null with no number', () => {
    expect(parseNumber('no figures here')).toBeNull();
  });
});

describe('parseFinancialFacts', () => {
  it('extracts standard line items with units', () => {
    const text = [
      'Findings (evidence-backed):',
      '- Total revenue of 4.2 billion USD for FY2025, up 8% year over year.',
      '- Net income was 610 million USD in FY2025.',
      '- Gross margin of 42.5% for the year.',
      '- Diluted EPS of 3.15.',
    ].join('\n');
    const facts = parseFinancialFacts(text);
    const byKey = Object.fromEntries(facts.map((f) => [f.key, f]));
    expect(byKey.revenue.value).toBe(4.2e9);
    expect(byKey.revenue.unit).toBe('currency');
    expect(byKey.netIncome.value).toBe(6.1e8);
    expect(byKey.grossMargin.value).toBe(42.5);
    expect(byKey.grossMargin.unit).toBe('percent');
    expect(byKey.eps.value).toBe(3.15);
  });

  it('does not misread a currency figure as a margin', () => {
    // "gross margin" keyword but no % → must be rejected, not emitted as percent.
    const facts = parseFinancialFacts('The gross margin trajectory improved over years of 2 billion in sales.');
    expect(facts.find((f) => f.key === 'grossMargin')).toBeUndefined();
    expect(facts.find((f) => f.key === 'revenue')?.value).toBe(2e9);
  });

  it('emits at most one fact per metric (first wins)', () => {
    const facts = parseFinancialFacts('Revenue 1 billion.\nRevenue 2 billion.');
    expect(facts.filter((f) => f.key === 'revenue')).toHaveLength(1);
    expect(facts.find((f) => f.key === 'revenue')?.value).toBe(1e9);
  });

  it('returns nothing for empty/no-number text', () => {
    expect(parseFinancialFacts(null)).toEqual([]);
    expect(parseFinancialFacts('The company makes widgets and is based in Karachi.')).toEqual([]);
  });

  it('keeps the source sentence as evidence', () => {
    const [fact] = parseFinancialFacts('- Free cash flow of 1.1 billion USD.');
    expect(fact.key).toBe('freeCashFlow');
    expect(fact.raw).toContain('Free cash flow');
  });
});
