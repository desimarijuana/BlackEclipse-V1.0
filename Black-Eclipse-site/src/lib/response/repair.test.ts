import { describe, it, expect } from 'vitest';
import { responseBlockMeta } from './schema-meta';
import { repairUnknownBlock } from './repair';
import { finalizeResponse } from './finalize';

function chartMeta() {
  const meta = responseBlockMeta().get('chart');
  expect(meta).toBeTruthy();
  return meta!;
}

describe('schema-meta introspection (drives repair, cannot drift)', () => {
  it('exposes chart field kinds, the chartType enum and the series item shape', () => {
    const fields = chartMeta().fields;
    const chartType = fields.find((f) => f.name === 'chartType');
    expect(chartType?.kind).toBe('enum');
    expect(chartType?.enumValues).toContain('bar');
    expect(chartType?.required).toBe(true);

    const series = fields.find((f) => f.name === 'series');
    expect(series?.kind).toBe('array');
    expect(series?.required).toBe(true);
    const name = series?.element?.fields?.find((f) => f.name === 'name');
    expect(name?.required).toBe(true);
    expect(name?.kind).toBe('string');
  });

  it('flags defaulted/optional fields as not required', () => {
    const tone = chartMeta().fields.find((f) => f.name === 'legend');
    expect(tone?.kind).toBe('boolean');
    expect(tone?.required).toBe(false);
  });
});

describe('repairUnknownBlock — generic, schema-directed', () => {
  it('nearest-matches a required enum value (bars → bar)', () => {
    const meta = chartMeta().fields;
    const repaired = repairUnknownBlock(
      { type: 'chart', chartType: 'bars', categories: ['a'], series: [{ name: 'S', data: [1] }] },
      meta,
    ) as Record<string, unknown>;
    expect(repaired.chartType).toBe('bar');
  });

  it('rescues a missing required field from a same-kind sibling (title → name)', () => {
    const meta = chartMeta().fields;
    const repaired = repairUnknownBlock(
      { type: 'chart', chartType: 'bar', categories: ['a'], series: [{ title: 'My series', data: [1] }] },
      meta,
    ) as Record<string, unknown>;
    const series = repaired.series as Record<string, unknown>[];
    expect(series[0].name).toBe('My series');
  });

  it('wraps a single value where an array is required, and coerces scalars', () => {
    const meta = responseBlockMeta().get('data_table')!.fields;
    const repaired = repairUnknownBlock(
      { type: 'data_table', columns: ['A'], rows: { A: '1' } },
      meta,
    ) as Record<string, unknown>;
    expect(Array.isArray(repaired.rows)).toBe(true);
    expect((repaired.rows as unknown[])[0]).toEqual({ A: '1' });
  });

  it('never throws and is a no-op without metadata', () => {
    for (const raw of [null, 1, 'x', [], {}, { type: 'x' }]) {
      expect(() => repairUnknownBlock(raw, undefined)).not.toThrow();
    }
  });
});

describe('finalizeResponse — repair before degrade (renders the intended visual)', () => {
  it('repairs a flow whose steps used `title` instead of `label`', () => {
    const result = finalizeResponse({ blocks: [{ type: 'flow', steps: [{ title: 'Only step' }] }] });
    expect(result.response.blocks[0].type).toBe('flow');
    expect(result.degraded.some((d) => d.code === 'BLOCK_REPAIRED')).toBe(true);
    expect(result.degraded.every((d) => d.code !== 'BLOCK_DEGRADED')).toBe(true);
  });

  it('repairs citations whose sources used a novel `headline`', () => {
    const result = finalizeResponse({
      blocks: [{ type: 'citations', sources: [{ headline: 'CPI Sep', url: 'https://www.bls.gov/cpi/' }] }],
    });
    const block = result.response.blocks[0];
    expect(block.type).toBe('citations');
    if (block.type === 'citations') expect(block.sources[0].title).toBe('CPI Sep');
  });

  it('repairs a chart with a wrong enum and a renamed series field — renders as a chart', () => {
    const result = finalizeResponse({
      blocks: [{ type: 'chart', chartType: 'bars', categories: ['a', 'b'], series: [{ title: 'P', data: [1, 2] }] }],
    });
    const block = result.response.blocks[0];
    expect(block.type).toBe('chart');
    if (block.type === 'chart') {
      expect(block.chartType).toBe('bar');
      expect(block.series[0].name).toBe('P');
    }
  });

  it('coerces a stringified boolean', () => {
    const result = finalizeResponse({
      blocks: [{ type: 'details', summary: 'More', markdown: 'x', open: 'true' }],
    });
    const block = result.response.blocks[0];
    expect(block.type).toBe('details');
    if (block.type === 'details') expect(block.open).toBe(true);
  });

  it('still degrades when a required field cannot be recovered (no invention)', () => {
    const result = finalizeResponse({ blocks: [{ type: 'chart', chartType: 'bar', categories: ['a'] }] });
    const block = result.response.blocks[0];
    expect(block.type).toBe('markdown');
    expect(result.degraded.some((d) => d.code === 'BLOCK_DEGRADED')).toBe(true);
  });

  it('the repaired block is a real rendered type, never `unknown`', () => {
    for (const payload of [
      { type: 'flow', steps: [{ title: 'A' }] },
      { type: 'citations', sources: [{ headline: 'H', url: 'https://x.com' }] },
      { type: 'chart', chartType: 'bars', categories: ['a'], series: [{ title: 'P', data: [1] }] },
    ]) {
      const result = finalizeResponse({ blocks: [payload] });
      expect(result.response.blocks[0].type).not.toBe('unknown');
      expect(result.response.blocks[0].type).not.toBe('markdown');
    }
  });
});
