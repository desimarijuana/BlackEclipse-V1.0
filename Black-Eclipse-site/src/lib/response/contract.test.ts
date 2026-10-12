import { describe, it, expect } from 'vitest';
import {
  parseResponsePayload,
  validateBlock,
  RESPONSE_SCHEMA_VERSION,
  RESPONSE_LIMITS,
} from './contract';

describe('response contract', () => {
  it('parses a valid envelope and validates every block', () => {
    const parsed = parseResponsePayload({
      schemaVersion: '1.0',
      title: 'Bitcoin vs Ethereum',
      blocks: [
        { type: 'markdown', markdown: 'An **evidence-backed** comparison.' },
        { type: 'metric_grid', metrics: [{ label: 'BTC return', value: 12.4, unit: '%', delta: 12.4 }] },
        { type: 'chart', chartType: 'line', categories: ['d1', 'd2'], series: [{ name: 'BTC', data: [1, 2] }] },
      ],
    });
    expect(parsed.schemaVersion).toBe('1.0');
    expect(parsed.title).toBe('Bitcoin vs Ethereum');
    expect(parsed.blocks).toHaveLength(3);
    expect(parsed.blocks.map((b) => b.type)).toEqual(['markdown', 'metric_grid', 'chart']);
    expect(parsed.diagnostics).toHaveLength(0);
  });

  it('degrades an unknown block type to a diagnostic without losing siblings', () => {
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'markdown', markdown: 'kept' },
        { type: 'hologram', data: [1, 2, 3] },
      ],
    });
    expect(parsed.blocks[0].type).toBe('markdown');
    expect(parsed.blocks[1].type).toBe('unknown');
    expect(parsed.diagnostics.some((d) => d.code === 'BLOCK_INVALID')).toBe(true);
    expect(parsed.diagnostics[0].declaredType).toBe('hologram');
  });

  it('rejects a chart with no series but keeps the rest', () => {
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'chart', chartType: 'line', series: [] },
        { type: 'markdown', markdown: 'survivor' },
      ],
    });
    expect(parsed.blocks[0].type).toBe('unknown');
    expect(parsed.blocks[1].type).toBe('markdown');
  });

  it('marks unavailable metrics explicitly', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'metric_grid', metrics: [{ label: 'Beta', value: 'UNAVAILABLE', unavailable: true }] }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('metric_grid');
    if (block.type === 'metric_grid') {
      expect(block.metrics[0].unavailable).toBe(true);
    }
  });

  it('recursively validates nested tab blocks', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'tabs',
          tabs: [
            { label: 'One', blocks: [{ type: 'markdown', markdown: 'a' }] },
            { label: 'Two', blocks: [{ type: 'bogus' }] },
          ],
        },
      ],
    });
    const tabs = parsed.blocks[0];
    expect(tabs.type).toBe('tabs');
    if (tabs.type === 'tabs') {
      expect((tabs.tabs[0].blocks[0] as { type: string }).type).toBe('markdown');
      expect((tabs.tabs[1].blocks[0] as { type: string }).type).toBe('unknown');
    }
  });

  it('warns (but renders) on a newer schema major', () => {
    const parsed = parseResponsePayload({
      schemaVersion: '2.0',
      blocks: [{ type: 'markdown', markdown: 'future' }],
    });
    expect(parsed.diagnostics.some((d) => d.code === 'SCHEMA_VERSION_FUTURE')).toBe(true);
    expect(parsed.blocks).toHaveLength(1);
  });

  it('returns an empty diagnostic-backed response for a non-object payload', () => {
    const parsed = parseResponsePayload('not an object');
    expect(parsed.blocks).toHaveLength(0);
    expect(parsed.diagnostics[0].code).toBe('ENVELOPE_INVALID');
  });

  it('reports when the envelope has no blocks', () => {
    const parsed = parseResponsePayload({ blocks: [] });
    expect(parsed.schemaVersion).toBe(RESPONSE_SCHEMA_VERSION);
    expect(parsed.diagnostics.some((d) => d.code === 'NO_BLOCKS')).toBe(true);
  });

  it('validateBlock never throws on arbitrary input', () => {
    expect(validateBlock(null).block.type).toBe('unknown');
    expect(validateBlock(42).block.type).toBe('unknown');
    expect(validateBlock({ type: 7 }).block.type).toBe('unknown');
  });

  it('keeps bounded metadata through a valid envelope', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'markdown', markdown: 'ok' }],
      metadata: { model: 'x', latencyMs: 12 },
    });
    expect(parsed.blocks).toHaveLength(1);
    expect(parsed.metadata).toEqual({ model: 'x', latencyMs: 12 });
  });

  it('drops oversized metadata instead of failing the whole answer', () => {
    const tooManyKeys: Record<string, number> = {};
    for (let i = 0; i < RESPONSE_LIMITS.maxMetadataKeys + 1; i += 1) tooManyKeys[`k${i}`] = i;
    const parsed = parseResponsePayload({
      blocks: [{ type: 'markdown', markdown: 'survivor' }],
      metadata: tooManyKeys,
    });
    // The answer is preserved; only the unbounded bookkeeping is dropped.
    expect(parsed.blocks).toHaveLength(1);
    expect(parsed.metadata).toBeUndefined();
  });

  it('drops a metadata value larger than the string ceiling', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'markdown', markdown: 'survivor' }],
      metadata: { blob: 'x'.repeat(RESPONSE_LIMITS.maxStringLength + 1) },
    });
    expect(parsed.blocks).toHaveLength(1);
    expect(parsed.metadata).toBeUndefined();
  });
});
