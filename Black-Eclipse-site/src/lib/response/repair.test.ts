import { describe, it, expect } from 'vitest';
import { responseBlockMeta } from './schema-meta';
import { describeResponseBlocks } from '@/lib/harness/response-bridge';
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
    // The kind is OPTIONAL: a missing or unknown kind falls back to `auto` and
    // the director picks the kind from the data's shape. One odd (or missing)
    // kind must never cost the reader the whole chart - the same rule the mark
    // types already follow.
    expect(chartType?.required).toBe(false);

    const series = fields.find((f) => f.name === 'series');
    expect(series?.kind).toBe('array');
    // `series` is now OPTIONAL: a chart may arrive as a SCENE (panels of marks)
    // instead, so the simple form defaults to an empty array.
    expect(series?.required).toBe(false);
    const name = series?.element?.fields?.find((f) => f.name === 'name');
    expect(name?.required).toBe(true);
    expect(name?.kind).toBe('string');
  });

  it('exposes the SCENE form (panels of marks) so any chart can be drawn', () => {
    const fields = chartMeta().fields;
    const panels = fields.find((f) => f.name === 'panels');
    expect(panels?.kind).toBe('array');
    // The panel's own fields (one level in).
    const marks = panels?.element?.fields?.find((f) => f.name === 'marks');
    expect(marks?.kind).toBe('array');
    // The mark itself is an object - the shape the engine draws.
    expect(marks?.element?.kind).toBe('object');
  });

  it('tells the MODEL the whole mark vocabulary (the bridge read-back)', () => {
    // The repair meta is deliberately bounded, but the model must be able to
    // see every mark the engine can draw - otherwise "any chart" is a promise
    // the model cannot keep.
    const chart = describeResponseBlocks().find((b) => b.type === 'chart');
    const panels = chart?.fields.find((f) => f.name === 'panels');
    const marks = panels?.itemDetail?.find((f) => f.name === 'marks');
    const markType = marks?.itemDetail?.find((f) => f.name === 'type');
    expect(markType?.kind).toContain('violin');
    expect(markType?.kind).toContain('box');
    expect(markType?.kind).toContain('candlestick');
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
