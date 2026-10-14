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

  it('filters to one block type when asked', async () => {
    const out = await responseContractCapability({ op: 'schema', block_type: 'mermaid' });
    expect(out.status).toBe('OK');
    expect((out.blocks as { type: string }[]).map((b) => b.type)).toEqual(['mermaid']);
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
