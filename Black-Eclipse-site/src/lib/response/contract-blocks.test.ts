import { describe, it, expect } from 'vitest';
import { parseResponsePayload, validateBlock, RESPONSE_LIMITS } from './contract';
import { RESPONSE_ICONS, isResponseIconKey, resolveResponseIcon } from './icons';

describe('response block aliases', () => {
  it('maps `text` (+ content) to a markdown block', () => {
    const parsed = parseResponsePayload({
      blocks: [{ id: 'summary', type: 'text', content: 'The main findings.' }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('markdown');
    if (block.type === 'markdown') expect(block.markdown).toBe('The main findings.');
    expect(parsed.diagnostics).toHaveLength(0);
  });

  it('maps `table` to data_table', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'table',
          columns: [{ key: 'a', label: 'A' }],
          rows: [{ a: 1 }],
        },
      ],
    });
    expect(parsed.blocks[0].type).toBe('data_table');
  });

  it('maps `source_list` to citations', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'source_list', sources: [{ title: 'X', url: 'https://example.com' }] }],
    });
    expect(parsed.blocks[0].type).toBe('citations');
  });

  it('maps `interactive_form` to controls', () => {
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'interactive_form', controls: [{ kind: 'text', id: 'q', label: 'Query' }] },
      ],
    });
    expect(parsed.blocks[0].type).toBe('controls');
  });

  it('maps `execution_timeline` to timeline', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'execution_timeline', events: [{ time: 't0', title: 'Started' }] }],
    });
    expect(parsed.blocks[0].type).toBe('timeline');
  });
});

describe('new rich blocks', () => {
  it('validates a stepper and defaults step status', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'stepper', steps: [{ title: 'Fetch' }, { title: 'Analyze', status: 'done' }] }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('stepper');
    if (block.type === 'stepper') {
      expect(block.steps[0].status).toBe('pending');
      expect(block.steps[1].status).toBe('done');
    }
  });

  it('validates an infographic with icon keys', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'infographic',
          cards: [
            { icon: 'trend-up', label: 'Return', value: 12.4, unit: '%' },
            { icon: 'not-a-real-icon', label: 'Sharpe', value: 1.8 },
          ],
        },
      ],
    });
    expect(parsed.blocks[0].type).toBe('infographic');
    // The contract keeps the raw key; the renderer resolves/degrades it.
    expect(parsed.diagnostics).toHaveLength(0);
  });

  it('validates a report and recursively validates nested blocks', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'report',
          title: 'Q3 Review',
          sections: [
            { heading: 'Summary', markdown: 'text', blocks: [{ type: 'markdown', markdown: 'nested' }] },
            { heading: 'Bad', blocks: [{ type: 'bogus' }] },
          ],
        },
      ],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('report');
    if (block.type === 'report') {
      expect((block.sections[0].blocks as { type: string }[])[0].type).toBe('markdown');
      expect((block.sections[1].blocks as { type: string }[])[0].type).toBe('unknown');
    }
    expect(parsed.diagnostics.some((d) => d.code === 'BLOCK_INVALID')).toBe(true);
  });

  it('validates a node_graph', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'node_graph',
          nodes: [{ id: 'a', label: 'A', detail: 'start' }, { id: 'b', label: 'B' }],
          edges: [{ from: 'a', to: 'b' }],
        },
      ],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('node_graph');
    if (block.type === 'node_graph') expect(block.direction).toBe('LR');
  });

  it('validates an action_group', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'action_group',
          actions: [{ id: 'a1', label: 'Run stress test', prompt: 'Run a stress test on the portfolio' }],
        },
      ],
    });
    expect(parsed.blocks[0].type).toBe('action_group');
  });

  it('validates an artifact reference', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'artifact', artifacts: [{ artifactId: 'abc', name: 'report.pdf', category: 'report' }] }],
    });
    expect(parsed.blocks[0].type).toBe('artifact');
  });

  it('rejects an oversized stepper without losing sibling blocks', () => {
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'stepper', steps: Array.from({ length: RESPONSE_LIMITS.maxSteps + 1 }, (_, i) => ({ title: `s${i}` })) },
        { type: 'markdown', markdown: 'survivor' },
      ],
    });
    expect(parsed.blocks[0].type).toBe('unknown');
    expect(parsed.blocks[1].type).toBe('markdown');
  });
});

describe('link scheme safety', () => {
  it('rejects a javascript: URL in citations (block degrades, not executed)', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'citations', sources: [{ title: 'evil', url: 'javascript:alert(1)' }] }],
    });
    expect(parsed.blocks[0].type).toBe('unknown');
  });

  it('rejects a data: URL in an artifact', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'artifact', artifacts: [{ name: 'x', url: 'data:text/html,<script>alert(1)</script>' }] }],
    });
    expect(parsed.blocks[0].type).toBe('unknown');
  });

  it('accepts a normal https URL', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'citations', sources: [{ title: 'ok', url: 'https://example.com/a' }] }],
    });
    expect(parsed.blocks[0].type).toBe('citations');
  });
});

describe('icon registry', () => {
  it('resolves allowlisted keys and degrades unknown ones to the default', () => {
    expect(isResponseIconKey('trend-up')).toBe(true);
    expect(isResponseIconKey('nope')).toBe(false);
    expect(resolveResponseIcon('trend-up')).toBe(RESPONSE_ICONS['trend-up']);
    expect(resolveResponseIcon('nope')).toBe(resolveResponseIcon(undefined));
  });
});

describe('validateBlock total behavior', () => {
  it('never throws on the new block types', () => {
    for (const raw of [null, 5, { type: 'stepper' }, { type: 'artifact' }, { type: 'node_graph', nodes: [] }]) {
      expect(() => validateBlock(raw)).not.toThrow();
    }
  });
});
