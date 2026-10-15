import { describe, it, expect, afterEach } from 'vitest';
import {
  finalizeResponse,
  finalizeParsed,
  finalizeFenceSource,
  degradeUnknownBlock,
  setResponseDegradeReporter,
} from './finalize';
import { parseResponsePayload } from './contract';

const noUnknown = (r: ReturnType<typeof finalizeResponse>): boolean =>
  r.response.blocks.every((b) => b.type !== 'unknown');
const noErrors = (r: ReturnType<typeof finalizeResponse>): boolean =>
  r.response.diagnostics.every((d) => d.severity !== 'error');

describe('finalizeResponse — the render guarantee', () => {
  it('keeps a drifted-but-recoverable chart as a real chart (normalization, no degrade)', () => {
    const result = finalizeResponse({
      blocks: [
        {
          type: 'chart',
          chartType: 'bar',
          labels: ['4,000', '4,450'],
          datasets: [{ label: 'P(>)', data: [53.8, 21.7] }],
        },
      ],
    });
    expect(result.degraded).toHaveLength(0);
    expect(result.response.blocks[0].type).toBe('chart');
  });

  it('degrades a rejected block to readable content (never `unknown`, never an error)', () => {
    const result = finalizeResponse({
      blocks: [
        { type: 'markdown', markdown: 'KEEP' },
        { type: 'hologram', title: 'Nova', data: [1, 2] },
      ],
    });
    expect(noUnknown(result)).toBe(true);
    expect(noErrors(result)).toBe(true);
    expect(result.degraded.some((d) => d.declaredType === 'hologram')).toBe(true);
    const degraded = result.response.blocks[1];
    expect(degraded.type).toBe('markdown');
    if (degraded.type === 'markdown') expect(degraded.markdown).toContain('Nova');
    expect(result.response.blocks[0].type).toBe('markdown');
  });

  it('rescues the block’s own prose when a rejected block carries it', () => {
    const result = finalizeResponse({ blocks: [{ type: 'not_a_block', text: 'REAL CONTENT' }] });
    const block = result.response.blocks[0];
    expect(block.type).toBe('markdown');
    if (block.type === 'markdown') expect(block.markdown).toContain('REAL CONTENT');
  });

  it('degrades a non-object / invalid envelope to readable content, not an empty error', () => {
    const result = finalizeResponse('just a string');
    expect(noUnknown(result)).toBe(true);
    expect(noErrors(result)).toBe(true);
    expect(result.response.blocks).toHaveLength(1);
  });

  it('degrades unknown blocks nested inside tabs, report and carousel', () => {
    const result = finalizeResponse({
      blocks: [
        { type: 'tabs', tabs: [{ label: 'T', blocks: [{ type: 'bogus', text: 'IN_TAB' }] }] },
        {
          type: 'report',
          sections: [{ heading: 'S', blocks: [{ type: 'bogus', text: 'IN_REPORT' }] }],
        },
        { type: 'carousel', slides: [{ label: 'C', blocks: [{ type: 'bogus', text: 'IN_CAROUSEL' }] }] },
      ],
    });
    expect(noUnknown(result)).toBe(true);
    expect(JSON.stringify(result.response.blocks)).toContain('IN_TAB');
    expect(JSON.stringify(result.response.blocks)).toContain('IN_REPORT');
    expect(JSON.stringify(result.response.blocks)).toContain('IN_CAROUSEL');
  });

  it('an empty valid envelope stays quiet (no invented content)', () => {
    const result = finalizeResponse({ blocks: [] });
    expect(result.degraded).toHaveLength(0);
    expect(result.response.blocks).toHaveLength(0);
  });
});

describe('finalizeFenceSource — malformed JSON never becomes an error card', () => {
  it('degrades malformed JSON to a code fence and records the reason', () => {
    const result = finalizeFenceSource('{ not json }');
    expect(result.response.blocks[0].type).toBe('markdown');
    expect(result.degraded[0].code).toBe('MALFORMED_JSON');
  });

  it('finalizes valid JSON normally', () => {
    const result = finalizeFenceSource('{"blocks":[{"type":"markdown","markdown":"OK"}]}');
    expect(result.degraded).toHaveLength(0);
    expect(result.response.blocks[0].type).toBe('markdown');
  });

  it('an empty source yields an empty, quiet response', () => {
    const result = finalizeFenceSource('   ');
    expect(result.response.blocks).toHaveLength(0);
    expect(result.degraded).toHaveLength(0);
  });
});

describe('finalizeParsed — downgrades error diagnostics', () => {
  it('maps every error diagnostic to a non-fatal note and records it', () => {
    const parsed = parseResponsePayload({ blocks: [{ type: 'markdown', markdown: 'x' }, { type: 'hologram' }] });
    expect(parsed.diagnostics.some((d) => d.severity === 'error')).toBe(true);
    const result = finalizeParsed(parsed);
    expect(noErrors(result)).toBe(true);
    expect(result.degraded.length).toBeGreaterThan(0);
  });
});

describe('degradeUnknownBlock', () => {
  it('never throws on any input shape', () => {
    for (const raw of [null, undefined, 42, 'text', [], { a: 1 }, { type: 'x' }]) {
      expect(() => degradeUnknownBlock(raw)).not.toThrow();
      expect(degradeUnknownBlock(raw).type).toBe('markdown');
    }
  });
});

describe('the chokepoint invariant holds over an adversarial corpus', () => {
  const corpus: unknown[] = [
    'not an object',
    42,
    null,
    [],
    {},
    { blocks: 'nope' },
    { blocks: [{ type: 'chart', labels: ['a'], datasets: [{ label: 'L', data: [1] }] }] },
    { blocks: [{ type: 'flow', steps: [{ label: 'A', tone: 'trend-up' }] }] },
    { blocks: [{ type: 'citations', items: [{ label: 'CPI', source: 'BLS', url: 'https://bls.gov' }] }] },
    { blocks: [{ type: 'hologram', data: [1, 2, 3] }] },
    { blocks: [{ type: 'data_table', columns: ['A', 'B'], rows: [['1', '2']] }] },
    { blocks: [{ type: 'metric_grid' }] },
    { schemaVersion: '99', blocks: [{ type: 'markdown', markdown: 'future' }] },
  ];

  it('produces no `unknown` block and no error diagnostic for any input', () => {
    for (const raw of corpus) {
      const result = finalizeResponse(raw);
      expect(noUnknown(result)).toBe(true);
      expect(noErrors(result)).toBe(true);
    }
  });
});

describe('degrade telemetry seam', () => {
  afterEach(() => setResponseDegradeReporter(null));

  it('reports degraded records to an installed reporter', () => {
    const seen: string[] = [];
    setResponseDegradeReporter((records) => seen.push(...records.map((r) => r.code)));
    finalizeResponse({ blocks: [{ type: 'hologram' }] });
    expect(seen.length).toBeGreaterThan(0);
  });
});
