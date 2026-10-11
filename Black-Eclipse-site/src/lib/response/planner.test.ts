import { describe, it, expect } from 'vitest';
import { planMarkdown, plannerUpgraded } from './planner';

describe('planMarkdown', () => {
  it('leaves plain prose as a single markdown block (unchanged rendering)', () => {
    const response = planMarkdown('Just a sentence.\n\nAnd another.');
    expect(response.blocks).toHaveLength(1);
    expect(response.blocks[0].type).toBe('markdown');
    expect(plannerUpgraded(response)).toBe(false);
  });

  it('upgrades a GFM table to an interactive data_table', () => {
    const md = [
      'Here is the comparison:',
      '',
      '| Metric | BTC | ETH |',
      '| --- | ---: | ---: |',
      '| Return | 12.4 | 8.1 |',
      '',
      'Conclusion follows.',
    ].join('\n');
    const response = planMarkdown(md);
    expect(plannerUpgraded(response)).toBe(true);
    const table = response.blocks.find((b) => b.type === 'data_table');
    expect(table).toBeTruthy();
    if (table && table.type === 'data_table') {
      expect(table.columns.map((c) => c.label)).toEqual(['Metric', 'BTC', 'ETH']);
      expect(table.columns[1].align).toBe('right');
      expect(table.rows).toHaveLength(1);
      expect(table.rows[0].c1).toBe('12.4');
    }
    // Prose is preserved around the table.
    expect(response.blocks.some((b) => b.type === 'markdown')).toBe(true);
  });

  it('upgrades a link-only Sources list to citations', () => {
    const md = [
      '### Sources',
      '- [SEC filing](https://www.sec.gov/edgar)',
      '- [Company IR](https://ir.example.com)',
    ].join('\n');
    const response = planMarkdown(md);
    const citations = response.blocks.find((b) => b.type === 'citations');
    expect(citations).toBeTruthy();
    if (citations && citations.type === 'citations') {
      expect(citations.sources).toHaveLength(2);
      expect(citations.sources[0].url).toBe('https://www.sec.gov/edgar');
    }
  });

  it('does not convert a prose list under a Sources heading', () => {
    const md = ['### Sources', '- A book about investing', '- Another book'].join('\n');
    const response = planMarkdown(md);
    expect(response.blocks.every((b) => b.type === 'markdown')).toBe(true);
  });

  it('never mis-detects a table inside a fenced code block', () => {
    const md = ['```', '| a | b |', '| --- | --- |', '| 1 | 2 |', '```'].join('\n');
    const response = planMarkdown(md);
    expect(response.blocks.every((b) => b.type === 'markdown')).toBe(true);
  });

  it('rejects a javascript: URL in a source list', () => {
    const md = ['### References', '- [evil](javascript:alert(1))'].join('\n');
    const response = planMarkdown(md);
    expect(response.blocks.some((b) => b.type === 'citations')).toBe(false);
  });
});
