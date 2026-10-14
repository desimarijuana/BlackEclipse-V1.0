import { describe, it, expect } from 'vitest';
import { parseResponsePayload, validateBlock, RESPONSE_LIMITS } from './contract';
import { RESPONSE_ICONS, isResponseIconKey, resolveResponseIcon, canonicalIconKey } from './icons';

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

  it('accepts `body` for the prose body of markdown/callout/details (observed producer output)', () => {
    // Reproduces real Sazgar/PSX answers: the model named the prose field
    // `body`, which previously failed every markdown/callout block as
    // BLOCK_INVALID and turned the answer into a diagnostics panel.
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'markdown', body: '**Short answer:** SAZEW assembles GWM vehicles.' },
        { type: 'callout', variant: 'warning', title: 'Limits', body: 'OCR was unavailable this run.' },
        { type: 'details', summary: 'More', body: 'HIDDEN' },
        { type: 'mermaid', title: 'Flow', body: 'flowchart TD\n A-->B' },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const [md, callout, details, mermaid] = parsed.blocks;
    expect(md.type).toBe('markdown');
    if (md.type === 'markdown') expect(md.markdown).toContain('SAZEW');
    expect(callout.type).toBe('callout');
    if (callout.type === 'callout') {
      expect(callout.tone).toBe('warning');
      expect(callout.markdown).toBe('OCR was unavailable this run.');
    }
    expect(details.type).toBe('details');
    if (details.type === 'details') expect(details.markdown).toBe('HIDDEN');
    expect(mermaid.type).toBe('mermaid');
    if (mermaid.type === 'mermaid') expect(mermaid.diagram).toContain('flowchart');
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

  it('accepts `key` item labels for key_value (observed producer output)', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'key_value',
          title: 'Invariants',
          items: [
            { key: 'Plan ≠ execution', value: 'A mandate is not a run.' },
            { key: 'Route health is per capability', value: 'web_search ok does not imply web_fetch ok.' },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('key_value');
    if (block.type === 'key_value') {
      expect(block.items[0].label).toBe('Plan ≠ execution');
      expect(block.items[1].label).toBe('Route health is per capability');
    }
  });

  it('accepts a long cited key_value value (observed producer output)', () => {
    const longValue =
      '"LSE Plaza (Formerly Lahore Stock Exchange Building)" — verified from the company\'s own page (https://lse.com.pk/LSEFinancialServices/LSE-plaza.php, retrieved 2026-10-13)';
    expect(longValue.length).toBeGreaterThan(120);
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'key_value',
          items: [{ key: 'What the building is', value: longValue }],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('key_value');
    if (block.type === 'key_value') expect(block.items[0].value).toBe(longValue);
  });

  it('accepts chart `series[].points` with {x,y} objects (observed scatter output)', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'scatter',
          xLabel: 'Volatility (%)',
          yLabel: 'Return (%)',
          series: [
            {
              name: 'Assets',
              points: [
                { x: 120.18, y: 28.32, label: 'BTC' },
                { x: 173.45, y: 35.46, label: 'ETH' },
              ],
            },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('chart');
    if (block.type === 'chart') {
      expect(block.series[0].data).toEqual([
        [120.18, 28.32],
        [173.45, 35.46],
      ]);
    }
  });

  it('accepts labelled scalar chart points and `labels` for categories', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chartType: 'bar',
          labels: ['Q1', 'Q2'],
          series: [{ name: 'Revenue', points: [{ value: 10 }, { value: 20 }] }],
        },
      ],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('chart');
    if (block.type === 'chart') {
      expect(block.categories).toEqual(['Q1', 'Q2']);
      expect(block.series[0].data).toEqual([10, 20]);
    }
  });

  it('accepts `chart_type` as the chart style field', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'chart',
          chart_type: 'line',
          series: [{ name: 'Close', data: [1, 2, 3] }],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('chart');
    if (block.type === 'chart') expect(block.chartType).toBe('line');
  });

  it('accepts `ticker`/`interval` and a day-count timeframe for financial_chart', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'financial_chart', ticker: 'BTC-USD', market: 'crypto', interval: '90d', style: 'candles' }],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('financial_chart');
    if (block.type === 'financial_chart') {
      expect(block.symbol).toBe('BTC-USD');
      expect(block.timeframe).toBe('1D');
      expect(block.chartType).toBe('candlestick');
    }
  });

  it('accepts `source` as the mermaid body', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'mermaid', source: 'flowchart LR\n A-->B' }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('mermaid');
    if (block.type === 'mermaid') expect(block.diagram).toContain('flowchart');
  });

  it('accepts `name`/`title` node labels and `source`/`target` edges', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'node_graph',
          nodes: [{ id: 'a', name: 'Ingest' }, { id: 'b', title: 'Train' }],
          edges: [{ source: 'a', target: 'b' }],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('node_graph');
    if (block.type === 'node_graph') {
      expect(block.nodes[0].label).toBe('Ingest');
      expect(block.nodes[1].label).toBe('Train');
      expect(block.edges[0]).toMatchObject({ from: 'a', to: 'b' });
    }
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

describe('website-style visual blocks', () => {
  it('validates a stat_hero with hero numbers and a delta', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'stat_hero',
          title: 'At a glance',
          stats: [
            { label: 'AUM', value: 4200000, prefix: '$', delta: 3.2, deltaTone: 'up' },
            { label: 'Drawdown', value: 'UNAVAILABLE', unavailable: true },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('stat_hero');
    if (block.type === 'stat_hero') {
      expect(block.stats[0].value).toBe(4200000);
      expect(block.stats[1].unavailable).toBe(true);
    }
  });

  it('maps the `stats`/`stat` alias onto stat_hero and labels from `name`', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'stat', stats: [{ name: 'Sharpe', value: 1.8 }] }],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('stat_hero');
    if (block.type === 'stat_hero') expect(block.stats[0].label).toBe('Sharpe');
  });

  it('validates a gauge and defaults max to 100 + tone to neutral', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'gauge', gauges: [{ label: 'Risk budget used', value: 62 }] }],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('gauge');
    if (block.type === 'gauge') {
      expect(block.gauges[0].max).toBe(100);
      expect(block.gauges[0].tone).toBe('neutral');
    }
  });

  it('maps the `progress` alias and `items` field onto a gauge', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'progress', items: [{ key: 'Completion', value: 40, max: 50 }] }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('gauge');
    if (block.type === 'gauge') expect(block.gauges[0].label).toBe('Completion');
  });

  it('validates a comparison_grid and normalizes string columns', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'comparison_grid',
          columns: ['Spot', { name: 'Futures', highlight: true }],
          rows: [
            { label: 'Leverage', values: [false, true] },
            { label: 'Fee', values: ['0.10%', '0.05%'] },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('comparison_grid');
    if (block.type === 'comparison_grid') {
      expect(block.columns.map((c) => c.label)).toEqual(['Spot', 'Futures']);
      expect(block.columns[1].highlight).toBe(true);
      expect(block.rows[0].values).toEqual([false, true]);
    }
  });

  it('validates a ranked_list and preserves producer order', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'ranked_list',
          valueLabel: 'Return %',
          items: [
            { label: 'BTC', value: 42.1 },
            { label: 'ETH', value: 18.4 },
            { label: 'SOL', value: 9.2 },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('ranked_list');
    if (block.type === 'ranked_list') expect(block.items.map((i) => i.label)).toEqual(['BTC', 'ETH', 'SOL']);
  });

  it('maps the `leaderboard` alias onto ranked_list', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'leaderboard', entries: [{ name: 'NVDA', value: 120 }] }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('ranked_list');
    if (block.type === 'ranked_list') expect(block.items[0].label).toBe('NVDA');
  });

  it('accepts an `unavailable` figure block with no data points (observed producer output)', () => {
    // Reproduces real answers: the model correctly reported UNAVAILABLE for a
    // figure with no retrievable data, but the block failed validation because
    // its data array was empty. The honest state must render, not error.
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'gauge',
          unavailable: true,
          label: 'Forward P/E',
          caption: 'needs: a ticker + forward EPS estimate (no consensus-estimate route is bound)',
        },
        {
          type: 'ranked_list',
          unavailable: true,
          title: 'Magnificent Seven — YTD return',
          caption: 'No rank available: no base close retrieved.',
        },
        { type: 'stat_hero', unavailable: true, title: 'Macro dashboard', caption: 'No macro route bound.' },
        { type: 'comparison_grid', unavailable: true, caption: 'Nothing to compare.' },
        { type: 'badge_row', unavailable: true, caption: 'No themes available.' },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const [gauge, ranked, hero, grid, badges] = parsed.blocks;
    expect(gauge.type).toBe('gauge');
    if (gauge.type === 'gauge') {
      expect(gauge.unavailable).toBe(true);
      expect(gauge.gauges).toEqual([]);
      expect(gauge.caption).toContain('consensus-estimate');
    }
    expect(ranked.type).toBe('ranked_list');
    if (ranked.type === 'ranked_list') expect(ranked.items).toEqual([]);
    expect(hero.type).toBe('stat_hero');
    if (hero.type === 'stat_hero') expect(hero.stats).toEqual([]);
    expect(grid.type).toBe('comparison_grid');
    if (grid.type === 'comparison_grid') {
      expect(grid.columns).toEqual([]);
      expect(grid.rows).toEqual([]);
    }
    expect(badges.type).toBe('badge_row');
    if (badges.type === 'badge_row') expect(badges.badges).toEqual([]);
  });

  it('validates a badge_row with tone + icon keys', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'badge_row',
          badges: [
            { label: 'AI', tone: 'info', icon: 'cpu' },
            { label: 'Semis' },
            { label: 'Energy', tone: 'warning' },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('badge_row');
    if (block.type === 'badge_row') {
      expect(block.badges).toHaveLength(3);
      expect(block.badges[1].tone).toBe('neutral');
    }
  });

  it('accepts bare-string badges (observed in a live probe run)', () => {
    // The model emitted `badges: ["PROBE-6 — badge_row"]`; a badge's only content
    // is its label, so the string is complete information — coerce, never drop.
    const parsed = parseResponsePayload({
      blocks: [{ type: 'badge_row', title: 'Themes', badges: ['AI', { label: 'Semis', tone: 'info' }] }],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('badge_row');
    if (block.type === 'badge_row') {
      expect(block.badges[0].label).toBe('AI');
      expect(block.badges[1].label).toBe('Semis');
    }
  });

  it('validates a carousel and recursively validates its nested slide blocks', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'carousel',
          title: 'Scenarios',
          slides: [
            { label: 'Base', blocks: [{ type: 'markdown', markdown: 'base case' }] },
            { label: 'Stress', blocks: [{ type: 'bogus' }] },
          ],
        },
      ],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('carousel');
    if (block.type === 'carousel') {
      expect((block.slides[0].blocks as { type: string }[])[0].type).toBe('markdown');
      expect((block.slides[1].blocks as { type: string }[])[0].type).toBe('unknown');
    }
    expect(parsed.diagnostics.some((d) => d.code === 'BLOCK_INVALID')).toBe(true);
  });

  it('maps the `slides` alias and `items` field onto a carousel', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'slides', items: [{ title: 'One', blocks: [{ type: 'markdown', markdown: 'x' }] }] }],
    });
    expect(parsed.blocks[0].type).toBe('carousel');
  });

  it('rejects an oversized ranked_list without losing sibling blocks', () => {
    const parsed = parseResponsePayload({
      blocks: [
        { type: 'ranked_list', items: Array.from({ length: RESPONSE_LIMITS.maxRankedItems + 1 }, (_, i) => ({ label: `l${i}`, value: i })) },
        { type: 'markdown', markdown: 'survivor' },
      ],
    });
    expect(parsed.blocks[0].type).toBe('unknown');
    expect(parsed.blocks[1].type).toBe('markdown');
  });

  it('never throws on the new block types', () => {
    for (const raw of [{ type: 'stat_hero' }, { type: 'gauge' }, { type: 'comparison_grid' }, { type: 'ranked_list' }, { type: 'badge_row' }, { type: 'carousel' }]) {
      expect(() => validateBlock(raw)).not.toThrow();
    }
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

describe('icon key canonicalization', () => {
  it('resolves case/separator spellings to the canonical key', () => {
    expect(canonicalIconKey('TrendUp')).toBe('trend-up');
    expect(canonicalIconKey('trend_up')).toBe('trend-up');
    expect(canonicalIconKey('TREND UP')).toBe('trend-up');
    expect(canonicalIconKey('ph-chart')).toBe('chart');
    expect(canonicalIconKey('brainCircuit')).toBe('brain-circuit');
  });

  it('maps common synonyms and emoji to a key', () => {
    expect(canonicalIconKey('graph')).toBe('chart');
    expect(canonicalIconKey('money')).toBe('dollar');
    expect(canonicalIconKey('alert')).toBe('warning');
    expect(canonicalIconKey('📈')).toBe('trend-up');
    expect(canonicalIconKey('⚠️')).toBe('warning');
  });

  it('keeps unknown strings as-is and drops non-strings', () => {
    expect(canonicalIconKey('not-a-real-icon')).toBe('not-a-real-icon');
    expect(canonicalIconKey(42)).toBeUndefined();
    expect(canonicalIconKey({ name: 'chart' })).toBeUndefined();
    expect(canonicalIconKey('  ')).toBeUndefined();
  });

  it('normalizes icons before validation for every icon-bearing block', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'infographic',
          cards: [
            { icon: 'TrendUp', label: 'Return', value: 12.4 },
            { icon: 42, label: 'Sharpe', value: 1.8 },
          ],
        },
        { type: 'ranked_list', items: [{ label: 'A', value: 1, icon: '📊' }] },
        { type: 'badge_row', badges: [{ label: 'AI', icon: 'brainCircuit' }] },
        { type: 'workflow', stages: [{ title: 'Fetch', icon: 'trend_up' }] },
        { type: 'stat_hero', stats: [{ label: 'AUM', value: 1, icon: '💰' }] },
        { type: 'action_group', actions: [{ id: 'a1', label: 'Do', prompt: 'do it', icon: 'settings' }] },
      ],
    });
    // Every block still validates — a bad icon costs the glyph, never the block.
    expect(parsed.diagnostics).toHaveLength(0);
    expect(parsed.blocks.map((b) => b.type)).toEqual([
      'infographic', 'ranked_list', 'badge_row', 'workflow', 'stat_hero', 'action_group',
    ]);
    const info = parsed.blocks[0];
    if (info.type === 'infographic') {
      expect(info.cards[0].icon).toBe('trend-up');
      expect(info.cards[1].icon).toBeUndefined();
    }
    const ranked = parsed.blocks[1];
    if (ranked.type === 'ranked_list') expect(ranked.items[0].icon).toBe('chart');
    const badges = parsed.blocks[2];
    if (badges.type === 'badge_row') expect(badges.badges[0].icon).toBe('brain-circuit');
    const flow = parsed.blocks[3];
    if (flow.type === 'workflow') expect(flow.stages[0].icon).toBe('trend-up');
    const hero = parsed.blocks[4];
    if (hero.type === 'stat_hero') expect(hero.stats[0].icon).toBe('dollar');
    const actions = parsed.blocks[5];
    if (actions.type === 'action_group') expect(actions.actions[0].icon).toBe('gears');
  });

  it('normalizes icons inside nested blocks too', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'report',
          sections: [
            { heading: 'S', blocks: [{ type: 'ranked_list', items: [{ label: 'A', value: 1, icon: 'TrendUp' }] }] },
          ],
        },
      ],
    });
    const report = parsed.blocks[0];
    if (report.type === 'report') {
      const nested = (report.sections[0].blocks as { type: string; items?: { icon?: string }[] }[])[0];
      expect(nested?.type).toBe('ranked_list');
      if (nested?.type === 'ranked_list') expect(nested.items?.[0]?.icon).toBe('trend-up');
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

describe('learning_map block', () => {
  it('parses a prerequisite-aware curriculum with resources', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'learning_map',
          title: 'Quant trading roadmap',
          goal: 'quantitative trading',
          pathId: 'path_abc',
          nodes: [
            { id: 'python', label: 'Python', level: 'beginner', resourceIds: ['r1'], objectives: ['write python'], assessment: 'script' },
            { id: 'quant', label: 'Quant trading', requires: ['python'], resourceIds: ['r2'] },
          ],
          resources: [
            { resourceId: 'r1', title: 'Python docs', url: 'https://docs.python.org/3/', type: 'documentation', durationSeconds: 120 },
            { resourceId: 'r2', title: 'Course', url: 'https://www.youtube.com/playlist?list=abc', type: 'video', thumbnail: 'https://i.ytimg.com/x.jpg' },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('learning_map');
    if (block.type === 'learning_map') {
      expect(block.nodes).toHaveLength(2);
      expect(block.nodes[0].status).toBe('pending');
      expect(block.nodes[1].requires).toEqual(['python']);
      expect(block.resources[0].cost ?? 'unknown').toBe('unknown');
    }
  });

  it('rejects a non-http(s) resource URL (no javascript: vector)', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'learning_map',
          nodes: [{ id: 'a', label: 'A' }],
          resources: [{ resourceId: 'r', title: 'x', url: 'javascript:alert(1)' }],
        },
      ],
    });
    expect(parsed.blocks[0].type).toBe('unknown');
    expect(parsed.diagnostics.length).toBeGreaterThan(0);
  });

  it('degrades a malformed learning_map without throwing', () => {
    expect(() => validateBlock({ type: 'learning_map', nodes: [] })).not.toThrow();
    const parsed = parseResponsePayload({ blocks: [{ type: 'learning_map' }] });
    expect(parsed.blocks[0].type).toBe('unknown');
  });
});
