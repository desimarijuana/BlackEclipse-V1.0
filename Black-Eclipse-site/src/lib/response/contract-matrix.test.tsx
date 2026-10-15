import { describe, it, expect } from 'vitest';
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { responseBlockMeta } from './schema-meta';
import { finalizeResponse } from './finalize';
import { REGISTERED_BLOCK_TYPES } from '@/components/response/response-view';
import { ResponseView } from '@/components/response/response-view';

// A canonical, minimal valid payload for EVERY registered block type. The parity
// tests below assert this map stays in lock-step with the contract, and that each
// sample renders cleanly (no repair, no degrade, no error) — the "render matrix".
const SAMPLES: Record<string, unknown> = {
  markdown: { type: 'markdown', markdown: 'text' },
  heading: { type: 'heading', text: 'H' },
  callout: { type: 'callout', markdown: 'c' },
  key_value: { type: 'key_value', items: [{ label: 'a', value: 1 }] },
  details: { type: 'details', summary: 's', markdown: 'm' },
  metric_grid: { type: 'metric_grid', metrics: [{ label: 'a', value: 1 }] },
  data_table: { type: 'data_table', columns: [{ key: 'a', label: 'A' }], rows: [{ a: 1 }] },
  chart: { type: 'chart', chartType: 'bar', series: [{ name: 's', data: [1] }] },
  diagram: { type: 'diagram', nodes: [{ id: 'a', label: 'A' }] },
  timeline: { type: 'timeline', events: [{ time: 't', title: 'T' }] },
  citations: { type: 'citations', sources: [{ title: 'X', url: 'https://x.com' }] },
  tabs: { type: 'tabs', tabs: [{ label: 'A', blocks: [{ type: 'markdown', markdown: 'x' }] }] },
  financial_chart: { type: 'financial_chart', symbol: 'BTC' },
  mermaid: { type: 'mermaid', diagram: 'flowchart LR\n A-->B' },
  controls: { type: 'controls', controls: [{ kind: 'text', id: 'q', label: 'Q' }] },
  stepper: { type: 'stepper', steps: [{ title: 'A' }] },
  infographic: { type: 'infographic', cards: [{ label: 'A' }] },
  workflow: { type: 'workflow', stages: [{ title: 'A' }] },
  flow: { type: 'flow', steps: [{ label: 'A' }] },
  report: { type: 'report', sections: [{ heading: 'S', markdown: 'm' }] },
  node_graph: { type: 'node_graph', nodes: [{ id: 'a', label: 'A' }] },
  action_group: { type: 'action_group', actions: [{ id: 'a1', label: 'A', prompt: 'p' }] },
  artifact: { type: 'artifact', artifacts: [{ name: 'a.txt' }] },
  gallery: { type: 'gallery', images: [{ url: 'https://x.com/i.png' }] },
  learning_map: { type: 'learning_map', nodes: [{ id: 'a', label: 'A' }] },
  stat_hero: { type: 'stat_hero', stats: [{ label: 'A', value: 1 }] },
  gauge: { type: 'gauge', gauges: [{ label: 'A', value: 1 }] },
  comparison_grid: { type: 'comparison_grid', columns: [{ label: 'A' }], rows: [{ label: 'r', values: [true] }] },
  ranked_list: { type: 'ranked_list', items: [{ label: 'A', value: 1 }] },
  badge_row: { type: 'badge_row', badges: [{ label: 'A' }] },
  carousel: { type: 'carousel', slides: [{ label: 'A', blocks: [{ type: 'markdown', markdown: 'x' }] }] },
};

const contractTypes = [...responseBlockMeta().keys()].sort();
const registered = [...REGISTERED_BLOCK_TYPES].sort();
const sampled = Object.keys(SAMPLES).sort();

describe('block-type parity (contract ↔ renderer ↔ matrix)', () => {
  it('the contract and the registered renderers agree exactly', () => {
    expect(registered).toEqual(contractTypes);
  });

  it('the render matrix covers every contract block type (adding a block fails here)', () => {
    expect(sampled).toEqual(contractTypes);
  });
});

describe('render matrix — every block type renders cleanly from a canonical payload', () => {
  const html = (node: ReactElement): string => renderToStaticMarkup(node);

  for (const type of contractTypes) {
    it(`\`${type}\` finalizes without repair/degrade and renders without an error`, () => {
      const sample = SAMPLES[type];
      const result = finalizeResponse({ blocks: [sample] });
      // The sample is canonical: nothing had to be repaired or degraded.
      expect(result.degraded).toEqual([]);
      expect(result.response.diagnostics.every((d) => d.severity !== 'error')).toBe(true);
      const block = result.response.blocks[0];
      expect(block?.type).toBe(type);

      // And it renders through the real renderer with no error affordance.
      const out = html(<ResponseView response={result.response} />);
      expect(out).not.toContain('Unsupported block type');
      expect(out).not.toContain('response diagnostic');
      expect(out).not.toContain('Could not render');
    });
  }
});
