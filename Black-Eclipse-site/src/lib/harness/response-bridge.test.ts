import { describe, it, expect } from 'vitest';
import { describeResponseBlocks, responseContractCapability } from './response-bridge';

describe('response contract bridge — schema read-back', () => {
  it('derives the field map live from the zod contract (no hand copy)', () => {
    const blocks = describeResponseBlocks();
    const types = blocks.map((b) => b.type);
    expect(types).toContain('markdown');
    expect(types).toContain('data_table');
    expect(types).toContain('mermaid');
    expect(types).toContain('gauge');
    expect(types.length).toBeGreaterThanOrEqual(25);

    const markdown = blocks.find((b) => b.type === 'markdown')!;
    expect(markdown.fields.map((f) => f.name)).toContain('markdown');
    expect(markdown.fields.find((f) => f.name === 'markdown')?.required).toBe(true);

    const table = blocks.find((b) => b.type === 'data_table')!;
    const columnField = table.fields.find((f) => f.name === 'columns')!;
    expect(columnField.kind).toContain('[]');
    expect(columnField.itemFields).toEqual(expect.arrayContaining(['key', 'label']));

    const callout = blocks.find((b) => b.type === 'callout')!;
    expect(callout.fields.find((f) => f.name === 'tone')?.kind).toContain('enum(');
  });

  it('reaches the chart mark vocabulary (3D included), not just the panel', () => {
    const chart = describeResponseBlocks().find((b) => b.type === 'chart')!;
    const panels = chart.fields.find((f) => f.name === 'panels')!;
    const marks = (panels.itemDetail ?? []).find((f) => f.name === 'marks')!;
    expect(marks.itemFields).toEqual(expect.arrayContaining(['type', 'x', 'y', 'z', 'matrix']));
    const type = (marks.itemDetail ?? []).find((f) => f.name === 'type')!;
    expect(type.kind).toContain('scatter3d');
    expect(type.kind).toContain('surface');
  });

  it('filters to one block type when asked', async () => {
    const out = await responseContractCapability({ op: 'schema', block_type: 'mermaid' });
    expect(out.status).toBe('OK');
    expect((out.blocks as { type: string }[]).map((b) => b.type)).toEqual(['mermaid']);
  });

  it('exposes the live icon-key vocabulary for the semantic icon fields', async () => {
    const out = await responseContractCapability({ op: 'schema', block_type: 'infographic' });
    expect(out.status).toBe('OK');
    const keys = out.iconKeys as string[];
    expect(keys).toContain('trend-up');
    expect(keys).toContain('brain-circuit');
    expect(keys).toContain('gears');
    expect(keys.length).toBeGreaterThanOrEqual(40);
    // Canonical lower-kebab spellings, no duplicates.
    expect(new Set(keys).size).toBe(keys.length);
    for (const key of keys) expect(key).toMatch(/^[a-z][a-z0-9-]*$/);
  });
});

describe('response contract bridge — validation read-back', () => {
  it('accepts a healthy fenced answer and reports every block', async () => {
    const markdown = [
      'Answer:',
      '```eclipse-response',
      JSON.stringify({
        blocks: [
          { type: 'markdown', markdown: 'hello' },
          { type: 'badge_row', badges: [{ label: 'AI' }, 'Semis'] },
        ],
      }),
      '```',
    ].join('\n');
    const out = await responseContractCapability({ op: 'validate', markdown });
    expect(out.status).toBe('OK');
    expect(out.ok).toBe(true);
    expect(out.blockCount).toBe(2);
  });

  it('reports the exact failing block and why', async () => {
    const markdown = JSON.stringify({
      blocks: [
        { type: 'markdown', markdown: 'fine' },
        { type: 'gauge', gauges: [{ label: 'x', value: 'not-a-number' }] },
        { type: 'markdown', body: 'also fine (aliased)' },
      ],
    });
    const out = await responseContractCapability({ op: 'validate', markdown });
    expect(out.status).toBe('OK');
    expect(out.ok).toBe(false);
    const blocks = out.blocks as { ok: boolean; type: string; error: string | null }[];
    expect(blocks[0].ok).toBe(true);
    expect(blocks[1].ok).toBe(false);
    expect(blocks[1].error).toContain('gauges.0.value');
    expect(blocks[2].ok).toBe(true);
  });

  it('validates the natural 3D surface shape (kind + flat z)', async () => {
    const markdown = JSON.stringify({
      blocks: [{
        type: 'chart',
        chartType: 'line',
        panels: [{
          marks: [{
            kind: 'surface', name: 'Sharpe',
            x: [5, 10], y: [20, 40], z: [0.4, 0.5, 0.6, 0.7],
          }],
        }],
      }],
    });
    const out = await responseContractCapability({ op: 'validate', markdown });
    expect(out.status).toBe('OK');
    expect(out.ok).toBe(true);
  });

  it('refuses an unsupported mark by name instead of passing it', async () => {
    const markdown = JSON.stringify({
      blocks: [{
        type: 'chart',
        chartType: 'line',
        panels: [{ marks: [{ type: 'waterfall3d', y: [1, 2] }] }],
      }],
    });
    const out = await responseContractCapability({ op: 'validate', markdown });
    expect(out.ok).toBe(false);
    const blocks = out.blocks as { ok: boolean; error: string | null }[];
    expect(blocks[0].ok).toBe(false);
    expect(blocks[0].error).toContain('waterfall3d');
  });

  it('reports malformed JSON as such', async () => {
    const out = await responseContractCapability({ op: 'validate', markdown: '```eclipse-response\n{"blocks": [}\n```' });
    expect(out.ok).toBe(false);
    expect(String(out.error)).toContain('malformed JSON');
  });

  it('reports a missing fence/payload honestly', async () => {
    const out = await responseContractCapability({ op: 'validate', markdown: 'just prose' });
    expect(out.ok).toBe(false);
    expect(String(out.error)).toContain('no eclipse-response fence');
  });

  it('rejects an unknown op instead of guessing', async () => {
    const out = await responseContractCapability({ op: 'drop-tables' });
    expect(out.status).toBe('UNAVAILABLE');
  });
});

describe('response contract bridge — finalize telemetry (Phase 4)', () => {
  it('reports a clean structured answer as neither repaired nor degraded', async () => {
    const markdown = JSON.stringify({ blocks: [{ type: 'markdown', markdown: 'hi' }] });
    const out = await responseContractCapability({ op: 'finalize', markdown });
    expect(out.status).toBe('OK');
    expect(out.blocks).toBe(1);
    expect(out.repaired).toBe(0);
    expect(out.degraded).toBe(0);
  });

  it('reports a schema-repaired block by type (the drift signal)', async () => {
    const markdown = JSON.stringify({
      blocks: [{ type: 'chart', chartType: 'bars', categories: ['a'], series: [{ title: 'P', data: [1] }] }],
    });
    const out = await responseContractCapability({ op: 'finalize', markdown });
    expect(out.status).toBe('OK');
    expect(out.repaired).toBe(1);
    expect(out.repairedTypes).toEqual(['chart']);
    expect(out.degraded).toBe(0);
  });

  it('reports a degraded block by type, and malformed JSON as `malformed`', async () => {
    const degraded = await responseContractCapability({
      op: 'finalize',
      markdown: JSON.stringify({ blocks: [{ type: 'hologram', data: [1] }] }),
    });
    expect(degraded.degraded).toBe(1);
    expect(degraded.degradedTypes).toEqual(['hologram']);

    const malformed = await responseContractCapability({ op: 'finalize', markdown: '```eclipse-response\n{ not json }\n```' });
    expect(malformed.degraded).toBe(1);
    expect(malformed.degradedTypes).toEqual(['malformed']);
  });

  it('a prose answer (no structured blocks) measures nothing', async () => {
    const out = await responseContractCapability({ op: 'finalize', markdown: 'just prose, no fence' });
    expect(out.status).toBe('OK');
    expect(out.blocks).toBe(0);
  });
});
