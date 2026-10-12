// ── Renderer integration tests (server-rendered) ───────────────────────────────
//
// These render the REAL components with `react-dom/server` in the node test
// environment, so they verify the registry dispatch, block content, ordering,
// error isolation and the streaming/malformed fences end-to-end — not a mock of
// the renderer. Client-only behaviour (ECharts/Mermaid canvas effects, clicks)
// is not exercised here; those paths are covered by the pure option/layout tests
// and the production build.

import { describe, it, expect } from 'vitest';
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseResponsePayload } from '@/lib/response/contract';
import type { ActionGroupBlock as ActionGroupBlockType } from '@/lib/response/contract';
import { parseFirstResponseFence } from '@/lib/response/parse';
import { ResponseView } from './response-view';
import { ResponseFence } from './response-fence';
import { Markdown } from '@/components/chat/markdown';
import { MetricGridBlock, CitationsBlock } from './blocks';
import { DataTableBlock } from './data-table-block';
import { DiagramBlock } from './diagram-block';
import { StepperBlock, InfographicBlock, ActionGroupBlock, ArtifactBlock } from './rich-blocks';
import { NodeGraphBlock } from './node-graph-block';

const html = (node: ReactElement): string => renderToStaticMarkup(node);

function view(payload: unknown, props: { onFollowup?: (p: string) => void } = {}): string {
  return html(<ResponseView response={parseResponsePayload(payload)} {...props} />);
}

describe('text-only answers still render (historical compatibility)', () => {
  it('renders a markdown-only response', () => {
    const out = view({ blocks: [{ type: 'markdown', markdown: 'Just **plain** text.' }] });
    expect(out).toContain('plain');
  });
});

describe('block rendering', () => {
  it('renders a metric grid and an explicit UNAVAILABLE chip (no invented value)', () => {
    const out = html(
      <MetricGridBlock
        metrics={[
          { label: 'Return', value: 12.4, unit: '%' },
          { label: 'Beta', value: 'UNAVAILABLE', unavailable: true },
        ]}
      />,
    );
    expect(out).toContain('Return');
    expect(out).toContain('12.4');
    expect(out).toContain('UNAVAILABLE');
  });

  it('renders a sortable/filterable data table with its rows', () => {
    const out = html(
      <DataTableBlock
        columns={[
          { key: 'a', label: 'Asset' },
          { key: 'b', label: 'Weight', align: 'right' },
        ]}
        rows={[
          { a: 'BTC', b: 40 },
          { a: 'ETH', b: 25 },
        ]}
      />,
    );
    expect(out).toContain('Asset');
    expect(out).toContain('Weight');
    expect(out).toContain('BTC');
    expect(out).toContain('2 rows');
  });

  it('renders inline Markdown in table cells and headers (bold is never literal)', () => {
    const out = html(
      <DataTableBlock
        columns={[{ key: 'a', label: '**Asset**' }]}
        rows={[{ a: '**BTC** with *risk*' }]}
      />,
    );
    expect(out).toContain('<strong');
    expect(out).toContain('<em');
    expect(out).not.toContain('**BTC**');
    expect(out).not.toContain('**Asset**');
  });

  it('renders a layered diagram with its nodes and an edge path', () => {
    const out = html(
      <DiagramBlock
        block={{
          type: 'diagram',
          diagramType: 'flowchart',
          direction: 'TB',
          nodes: [
            { id: 'a', label: 'Retrieve', tone: 'info' },
            { id: 'b', label: 'Analyze', tone: 'neutral' },
          ],
          edges: [{ from: 'a', to: 'b', tone: 'neutral' }],
        }}
      />,
    );
    expect(out).toContain('Retrieve');
    expect(out).toContain('Analyze');
    expect(out).toContain('<path');
  });

  it('renders a selectable node graph with detail markers', () => {
    const out = html(
      <NodeGraphBlock
        block={{
          type: 'node_graph',
          direction: 'LR',
          nodes: [
            { id: 'a', label: 'Ingest', tone: 'success', detail: 'Reads raw bars' },
            { id: 'b', label: 'Train', tone: 'neutral' },
          ],
          edges: [{ from: 'a', to: 'b', tone: 'neutral' }],
        }}
      />,
    );
    expect(out).toContain('Ingest');
    expect(out).toContain('Train');
    expect(out).toContain('role="button"');
    expect(out).toContain('Select a node to see its details.');
  });

  it('renders a stepper with per-step status', () => {
    const out = html(
      <StepperBlock
        block={{
          type: 'stepper',
          title: 'Pipeline',
          steps: [
            { title: 'Fetch prices', status: 'done' },
            { title: 'Run backtest', status: 'active' },
          ],
        }}
      />,
    );
    expect(out).toContain('Pipeline');
    expect(out).toContain('Fetch prices');
    expect(out).toContain('Run backtest');
  });

  it('renders an infographic with resolved icon cards', () => {
    const out = html(
      <InfographicBlock
        block={{
          type: 'infographic',
          cards: [{ icon: 'trend-up', label: 'CAGR', value: 9.2, unit: '%', tone: 'neutral' }],
        }}
      />,
    );
    expect(out).toContain('CAGR');
    expect(out).toContain('9.2');
    expect(out).toContain('<svg');
  });

  it('renders citations as safe external links', () => {
    const out = html(
      <CitationsBlock
        sources={[{ title: 'Example', url: 'https://example.com/a', source: 'web' }]}
      />,
    );
    expect(out).toContain('href="https://example.com/a"');
    expect(out).toContain('rel="noopener noreferrer"');
  });

  it('renders artifacts as links to the existing Artifact Center route', () => {
    const out = html(
      <ArtifactBlock block={{ type: 'artifact', artifacts: [{ artifactId: 'abc', name: 'report.pdf' }] }} />,
    );
    expect(out).toContain('report.pdf');
    expect(out).toContain('/api/artifacts/abc/download');
  });
});

describe('action groups are proposals, not executions', () => {
  const block: ActionGroupBlockType = {
    type: 'action_group',
    actions: [{ id: 'a1', label: 'Stress test', prompt: 'Run a stress test', tone: 'neutral' }],
  };

  it('disables actions when there is no chat context', () => {
    const out = html(<ActionGroupBlock block={block} />);
    expect(out).toContain('Proposed');
    expect(out).toContain('disabled');
    expect(out).toContain('Actions are unavailable in this view.');
  });

  it('enables actions (as prompts) when wired to the agent loop', () => {
    const out = html(<ActionGroupBlock block={block} onFollowup={() => {}} />);
    expect(out).not.toContain('disabled');
    expect(out).toContain('Sends the action as a new turn');
  });
});

describe('mixed response ordering and isolation', () => {
  it('preserves block order (text → metric → chart → citations)', () => {
    const out = view({
      blocks: [
        { type: 'markdown', markdown: 'ALPHA summary' },
        { type: 'metric_grid', metrics: [{ label: 'BRAVO', value: 1 }] },
        { type: 'chart', chartType: 'line', categories: ['x'], series: [{ name: 'CHARLIE', data: [1] }] },
        { type: 'citations', sources: [{ title: 'DELTA', url: 'https://example.com' }] },
      ],
    });
    const iA = out.indexOf('ALPHA');
    const iB = out.indexOf('BRAVO');
    const iD = out.indexOf('DELTA');
    expect(iA).toBeGreaterThanOrEqual(0);
    expect(iB).toBeGreaterThan(iA);
    expect(iD).toBeGreaterThan(iB);
  });

  it('isolates an unknown block without discarding its siblings', () => {
    const out = view({
      blocks: [
        { type: 'markdown', markdown: 'SURVIVOR text' },
        { type: 'hologram', data: [1, 2] },
      ],
    });
    expect(out).toContain('SURVIVOR text');
    expect(out).toContain('Unsupported block type');
    expect(out).toContain('hologram');
    // The diagnostic panel lists the failure rather than swallowing it.
    expect(out).toContain('BLOCK_INVALID');
  });

  it('renders a nested report section with its own blocks', () => {
    const out = view({
      blocks: [
        {
          type: 'report',
          title: 'Review',
          sections: [
            { heading: 'Findings', markdown: 'INNER markdown', blocks: [{ type: 'markdown', markdown: 'DEEPER block' }] },
          ],
        },
      ],
    });
    expect(out).toContain('Review');
    expect(out).toContain('Findings');
    expect(out).toContain('INNER markdown');
    expect(out).toContain('DEEPER block');
  });
});

describe('workflow block (icon-driven connected process)', () => {
  it('renders each stage with its title and description through the registry', () => {
    const out = view({
      blocks: [
        {
          type: 'workflow',
          title: 'How HFT works',
          stages: [
            { icon: 'radio', title: 'Market data', description: 'Live prices' },
            { icon: 'brain-circuit', title: 'Strategy engine', description: 'Detects opportunities' },
            { icon: 'zap', title: 'Execution engine', description: 'Routes orders' },
            { icon: 'combined-chart', title: 'Monitoring and risk', description: 'Tracks fills' },
          ],
        },
      ],
    });
    for (const t of ['How HFT works', 'Market data', 'Strategy engine', 'Execution engine', 'Monitoring and risk', 'Detects opportunities']) {
      expect(out).toContain(t);
    }
    expect(out).not.toContain('Unsupported block type');
  });

  it('offers expand-all only when a stage has detail, and starts collapsed', () => {
    const withDetail = view({ blocks: [{ type: 'workflow', stages: [{ title: 'A', detail: 'deeper' }] }] });
    expect(withDetail).toContain('Expand all');
    expect(withDetail).toContain('aria-expanded="false"');

    const noDetail = view({ blocks: [{ type: 'workflow', stages: [{ title: 'A' }, { title: 'B' }] }] });
    expect(noDetail).not.toContain('Expand all');
  });

  it('uses a horizontal-capable flow for <=4 stages and stacks vertically for many', () => {
    const four = view({ blocks: [{ type: 'workflow', stages: [{ title: 'a' }, { title: 'b' }, { title: 'c' }, { title: 'd' }] }] });
    expect(four).toContain('sm:flex-row');
    const many = view({ blocks: [{ type: 'workflow', stages: Array.from({ length: 6 }, (_, i) => ({ title: `s${i}` })) }] });
    expect(many).not.toContain('sm:flex-row');
  });

  it('does not crash on an unknown icon key', () => {
    const out = view({ blocks: [{ type: 'workflow', stages: [{ icon: 'not-real', title: 'Fallback stage' }] }] });
    expect(out).toContain('Fallback stage');
  });
});

describe('response layout cohesion (blocks read as one document)', () => {
  // Regression: every sibling block used to get the same `space-y-4` gap, so a
  // valid multi-block answer looked like a stack of detached cards. Adjacent
  // prose must flow tightly; a visual surface must keep a clear gap.
  it('flows adjacent prose blocks tightly, with no leading gap on the first', () => {
    const out = view({
      blocks: [
        { type: 'markdown', markdown: 'FIRST' },
        { type: 'markdown', markdown: 'SECOND' },
      ],
    });
    expect(out).toContain('<div class="mt-0">');
    expect(out).toContain('<div class="mt-2.5">');
    expect(out).not.toContain('mt-4');
  });

  it('separates a prose block from a visual surface block', () => {
    const out = view({
      blocks: [
        { type: 'markdown', markdown: 'PROSE' },
        { type: 'data_table', columns: [{ key: 'a', label: 'A' }], rows: [{ a: 'SURFACE' }] },
      ],
    });
    expect(out).toContain('<div class="mt-4">');
    expect(out).not.toContain('mt-2.5');
  });

  it('keeps a five-block callout/table answer cohesive (no detached-card stacking)', () => {
    const out = view({
      blocks: [
        { type: 'callout', markdown: 'CALLOUT text' },
        { type: 'markdown', markdown: 'CONTENT text' },
        { type: 'data_table', columns: [{ key: 'a', label: 'A' }], rows: [{ a: 'ROW1' }] },
        { type: 'data_table', columns: [{ key: 'b', label: 'B' }], rows: [{ b: 'ROW2' }] },
        { type: 'markdown', markdown: 'CLOSING text' },
      ],
    });
    // All content survives …
    for (const t of ['CALLOUT text', 'CONTENT text', 'ROW1', 'ROW2', 'CLOSING text']) {
      expect(out).toContain(t);
    }
    // … and the rhythm groups prose while separating the two table surfaces.
    expect(out).toContain('<div class="mt-2.5">'); // callout → markdown
    expect(out).toContain('<div class="mt-4">'); // markdown → table
  });

  it('applies the same rhythm inside nested report blocks', () => {
    const out = view({
      blocks: [
        {
          type: 'report',
          sections: [
            {
              heading: 'S',
              blocks: [
                { type: 'markdown', markdown: 'NESTED one' },
                { type: 'markdown', markdown: 'NESTED two' },
              ],
            },
          ],
        },
      ],
    });
    expect(out).toContain('<div class="mt-2.5">');
  });
});

describe('real producer payload regression (text/code field names)', () => {
  // Reproduces a real answer where the model used `text` for prose/callout bodies
  // and `code` for mermaid. Before the fix, the markdown + callout blocks were
  // dropped as "Unsupported block type" and the answer was gutted.
  it('renders markdown(text) + mermaid(code) + callout(text) without unsupported blocks', () => {
    const out = view({
      blocks: [
        { type: 'markdown', text: '## What HFT is\n\nSpeed, not strategy.' },
        { type: 'mermaid', code: 'sequenceDiagram\n A->>B: hi' },
        { type: 'callout', variant: 'warning', title: 'Material limits', text: 'Could not verify current share.' },
      ],
    });
    expect(out).not.toContain('Unsupported block type');
    expect(out).toContain('What HFT is');
    expect(out).toContain('Speed, not strategy.');
    expect(out).toContain('Material limits');
    expect(out).toContain('Could not verify current share.');
  });
});

describe('markdown integration (chat surface)', () => {
  it('renders a settled ```mermaid fence as a diagram, not a code block', () => {
    const out = html(<Markdown content={'```mermaid\ngraph TD\n  A-->B\n```'} />);
    expect(out).not.toContain('<pre');
    expect(out).not.toContain('graph TD');
  });

  it('keeps a streaming mermaid fence as text so a half-written diagram never errors', () => {
    const out = html(<Markdown content={'```mermaid\ngraph TD\n  A-->'} streaming />);
    expect(out).toContain('<pre');
  });

  it('still renders an ordinary code fence as code', () => {
    const out = html(<Markdown content={'```js\nconst x = 1;\n```'} />);
    expect(out).toContain('<pre');
    expect(out).toContain('const x = 1;');
  });

  it('renders an eclipse-response fence embedded in prose', () => {
    const md =
      'Intro paragraph.\n\n```eclipse-response\n' +
      JSON.stringify({ blocks: [{ type: 'markdown', markdown: 'EMBEDDED value' }] }) +
      '\n```\n';
    const out = html(<Markdown content={md} />);
    expect(out).toContain('Intro paragraph.');
    expect(out).toContain('EMBEDDED value');
  });
});

describe('streaming and malformed fences', () => {
  it('shows a composing placeholder for an in-progress block (no fake component)', () => {
    const out = html(<ResponseFence source={'{ "blocks": [ { "type": "mark'} streaming />);
    expect(out).toContain('Composing structured response');
  });

  it('shows an explicit diagnostic for malformed settled JSON (never a fake answer)', () => {
    const out = html(<ResponseFence source={'{ not json }'} />);
    expect(out).toContain('could not be parsed');
  });

  it('renders a valid fence through the full Markdown → decode → render path', () => {
    const stored =
      'Here is the result.\n\n```eclipse-response\n' +
      JSON.stringify({ schemaVersion: '1.0', blocks: [{ type: 'text', content: 'ROUNDTRIP value' }] }) +
      '\n```\n';
    const decoded = parseFirstResponseFence(stored);
    expect(decoded?.status).toBe('ok');
    if (decoded?.status === 'ok') {
      const out = html(<ResponseView response={decoded.response} />);
      expect(out).toContain('ROUNDTRIP value');
    }
  });
});
