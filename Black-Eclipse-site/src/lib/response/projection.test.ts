import { describe, expect, it } from 'vitest';
import { parseResponsePayload } from './contract';
import { projectContentMarkdown, toMarkdownProjection } from './projection';

function project(raw: unknown): string {
  return toMarkdownProjection(parseResponsePayload(raw));
}

describe('toMarkdownProjection', () => {
  it('keeps markdown prose and a title', () => {
    const out = project({ title: 'Risks', blocks: [{ type: 'markdown', markdown: 'Body text.' }] });
    expect(out).toContain('# Risks');
    expect(out).toContain('Body text.');
  });

  it('projects a data_table as a GFM table', () => {
    const out = project({
      blocks: [{ type: 'data_table', columns: [{ key: 'a', label: 'Alpha' }], rows: [{ a: 1 }] }],
    });
    expect(out).toContain('| Alpha |');
    expect(out).toContain('| 1 |');
  });

  it('projects a chart as its data table', () => {
    const out = project({
      blocks: [{ type: 'chart', chartType: 'line', categories: ['d1', 'd2'], series: [{ name: 'BTC', data: [1, 2] }] }],
    });
    expect(out).toContain('BTC');
    expect(out).toContain('| 1 | 2 |');
  });

  it('renders an unresolved figure reference as UNAVAILABLE, never the raw ref', () => {
    const out = project({
      blocks: [{ type: 'metric_grid', metrics: [{ label: 'Sharpe', value: { $ref: 'analysis:run#/outputs/sharpe' } }] }],
    });
    expect(out).toContain('UNAVAILABLE');
    expect(out).not.toContain('$ref');
  });

  it('describes an interactive simulation with its expanded default inputs/outputs', () => {
    const out = project({ blocks: [{ type: 'simulation', preset: 'risk_reward' }] });
    expect(out).toContain('Inputs');
    expect(out).toContain('Entry price');
    expect(out).toContain('Risk / reward');
  });

  it('flattens a layout container so nested content is not lost', () => {
    const out = project({ blocks: [{ type: 'layout', blocks: [{ type: 'markdown', markdown: 'Nested.' }] }] });
    expect(out).toContain('Nested.');
  });
});

describe('projectContentMarkdown', () => {
  it('keeps prose and projects the fence instead of copying raw JSON', () => {
    const content = [
      'Here is the summary.',
      '',
      '```eclipse-response',
      '{"blocks":[{"type":"metric_grid","metrics":[{"label":"Return","value":12.4,"unit":"%"}]}]}',
      '```',
    ].join('\n');
    const out = projectContentMarkdown(content);
    expect(out).toContain('Here is the summary.');
    expect(out).toContain('Return');
    expect(out).not.toContain('eclipse-response');
    expect(out).not.toContain('"blocks"');
  });

  it('leaves plain prose unchanged', () => {
    expect(projectContentMarkdown('Just prose.')).toBe('Just prose.');
  });
});
