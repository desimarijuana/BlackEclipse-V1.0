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

describe('producer field-name synonyms are normalized (not dropped)', () => {
  it('accepts `content` for the prose body of markdown/callout/details/mermaid', () => {
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'markdown', content: 'PROSE' },
        { type: 'callout', variant: 'warning', title: 'Heads up', content: 'CAREFUL' },
        { type: 'details', summary: 'More', content: 'HIDDEN' },
        { type: 'mermaid', content: 'flowchart LR\n A-->B' },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const [md, callout, details, mermaid] = parsed.blocks;
    expect(md.type).toBe('markdown');
    if (md.type === 'markdown') expect(md.markdown).toBe('PROSE');
    expect(callout.type).toBe('callout');
    if (callout.type === 'callout') expect(callout.tone).toBe('warning');
    expect(details.type).toBe('details');
    if (details.type === 'details') expect(details.markdown).toBe('HIDDEN');
    expect(mermaid.type).toBe('mermaid');
    if (mermaid.type === 'mermaid') expect(mermaid.diagram).toContain('flowchart');
  });

  it('accepts `text` for the prose body of markdown/callout/details (observed producer output)', () => {
    // Reproduces a real answer: the model used `text` (the same word as the
    // `text`→`markdown` type alias) as the body field, which previously lost the
    // markdown and callout blocks as "Invalid input".
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'markdown', text: '## Heading\n\nBody prose.' },
        { type: 'callout', variant: 'warning', title: 'Limits', text: 'Could not verify.' },
        { type: 'details', summary: 'More', text: 'HIDDEN' },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const [md, callout, details] = parsed.blocks;
    expect(md.type).toBe('markdown');
    if (md.type === 'markdown') expect(md.markdown).toContain('Body prose.');
    expect(callout.type).toBe('callout');
    if (callout.type === 'callout') {
      expect(callout.tone).toBe('warning');
      expect(callout.markdown).toBe('Could not verify.');
    }
    expect(details.type).toBe('details');
    if (details.type === 'details') expect(details.markdown).toBe('HIDDEN');
  });

  it('does not steal `text` from a heading (heading legitimately owns `text`)', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'heading', text: 'Section title', level: 2 }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('heading');
    if (block.type === 'heading') expect(block.text).toBe('Section title');
    expect(parsed.diagnostics).toHaveLength(0);
  });

  it('accepts `code` as the mermaid body (observed producer output)', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'mermaid', code: 'sequenceDiagram\n A->>B: hi' }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('mermaid');
    if (block.type === 'mermaid') expect(block.diagram).toContain('sequenceDiagram');
    expect(parsed.diagnostics).toHaveLength(0);
  });

  it('accepts `items` for citations and `name` for the source title', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'citations', items: [{ name: 'WFE release', url: 'https://example.com/a' }] }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('citations');
    if (block.type === 'citations') expect(block.sources[0].title).toBe('WFE release');
    expect(parsed.diagnostics).toHaveLength(0);
  });

  it('accepts string table columns and positional array rows', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'data_table',
          columns: ['Region', 'Growth'],
          rows: [
            ['Americas', '+20.3%'],
            ['EMEA', '+4.4%'],
          ],
        },
      ],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('data_table');
    if (block.type === 'data_table') {
      expect(block.columns.map((c) => c.label)).toEqual(['Region', 'Growth']);
      expect(block.rows[0][block.columns[0].key]).toBe('Americas');
      expect(block.rows[1][block.columns[1].key]).toBe('+4.4%');
    }
  });

  it('maps a yearly `financial_chart` timeframe onto a supported one', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'financial_chart', symbol: 'NVDA', market: 'US', timeframe: '1Y' }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('financial_chart');
    if (block.type === 'financial_chart') expect(block.timeframe).toBe('1M');
  });

  it('preserves a metric card `note` as its `hint`', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'metric_grid', metrics: [{ label: 'Cap', value: '1.2tr', note: 'WFE' }] }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('metric_grid');
    if (block.type === 'metric_grid') expect(block.metrics[0].hint).toBe('WFE');
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

  it('validates an icon-driven workflow and defaults layout to auto', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'workflow',
          title: 'How HFT works',
          stages: [
            { id: 'market-data', icon: 'radio', title: 'Market data', description: 'Live prices and order books' },
            { id: 'strategy', icon: 'brain-circuit', title: 'Strategy engine', description: 'Detects opportunities', detail: 'More', inputs: ['feeds'], outputs: ['signals'] },
            { icon: 'zap', title: 'Execution engine', description: 'Routes orders' },
            { icon: 'combined-chart', title: 'Monitoring and risk', description: 'Tracks fills and exposure' },
          ],
        },
      ],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('workflow');
    if (block.type === 'workflow') {
      expect(block.layout).toBe('auto');
      expect(block.stages).toHaveLength(4);
      expect(block.stages[1].inputs).toEqual(['feeds']);
    }
    expect(parsed.diagnostics).toHaveLength(0);
  });

  it('accepts `steps` as a synonym for workflow `stages` (observed producer output)', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'workflow', steps: [{ title: 'Step one' }, { title: 'Step two' }] }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('workflow');
    if (block.type === 'workflow') {
      expect(block.stages).toHaveLength(2);
      expect(block.stages[0].title).toBe('Step one');
    }
    expect(parsed.diagnostics).toHaveLength(0);
  });

  it('rejects an oversized workflow without losing sibling blocks', () => {
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'workflow', stages: Array.from({ length: RESPONSE_LIMITS.maxWorkflowStages + 1 }, (_, i) => ({ title: `s${i}` })) },
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

  it('allowlists the workflow icon vocabulary', () => {
    for (const key of ['workflow', 'radio', 'brain-circuit', 'combined-chart', 'cpu', 'server', 'gears']) {
      expect(isResponseIconKey(key)).toBe(true);
    }
  });
});

describe('validateBlock total behavior', () => {
  it('never throws on the new block types', () => {
    for (const raw of [null, 5, { type: 'stepper' }, { type: 'artifact' }, { type: 'node_graph', nodes: [] }]) {
      expect(() => validateBlock(raw)).not.toThrow();
    }
  });
});
