// ── AnatomyBlock render + interaction tests (server-rendered) ─────────────────
//
// Renders the REAL AnatomyBlock with `react-dom/server`. The drawing is
// SELF-CONTAINED (explicit fill/stroke attributes, no kit stylesheet), so these
// assertions lock that in: a regression back to CSS-class-driven paint (which
// rendered black-on-black when the stylesheet did not load) fails here. Client-only
// behaviour (the animation timer, button clicks) cannot run in the node test
// environment — there is no DOM harness in this repo — so this asserts the
// interactive AFFORDANCES are present and correctly wired.

import { describe, it, expect } from 'vitest';
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseResponsePayload, type AnatomyBlock as AnatomyBlockType } from '@/lib/response/contract';
import { AnatomyBlock } from './anatomy-block';

const html = (node: ReactElement): string => renderToStaticMarkup(node);

function blockOf(payload: Record<string, unknown>): AnatomyBlockType {
  const block = parseResponsePayload({ blocks: [{ type: 'anatomy', ...payload }] }).blocks[0];
  if (!block || block.type !== 'anatomy') throw new Error('failed to build an anatomy block');
  return block;
}

const figure = blockOf({
  title: 'BlackEclipse data path',
  fig: 'Fig. 01',
  description: 'How a market quote flows into the vault and out to the agent.',
  caption: 'The refinery, end to end.',
  readout: 'idle',
  legend: [
    { label: 'stored', mark: 'raised' },
    { label: 'live', mark: 'lit' },
  ],
  parts: [
    { id: 'hopper', x: -160, w: 60, d: 60, height: 40, label: 'ingest' },
    { id: 'vault', kind: 'cylinder', x: 0, y: 0, radius: 28, height: 80, label: 'vault' },
  ],
  wires: [{ from: 'hopper', to: 'vault', tone: 'success', flow: true }],
  stages: [
    { label: 'ingest', note: '3 scrapers feed the hopper', readout: 'filling', lit: ['hopper'] },
    { label: 'serve', note: 'routes fan out', readout: 'serving', lit: ['vault'] },
  ],
});

describe('AnatomyBlock — a figure, not just an image', () => {
  const out = html(<AnatomyBlock block={figure} />);

  it('renders a labelled isometric SVG with real geometry', () => {
    expect(out).toContain('<svg');
    expect(out).toContain('role="img"');
    // Tight, content-fitted viewBox (not the raw 0 0 W H box).
    expect(out).toMatch(/viewBox="-?\d/);
    // Both parts are labelled on the plane.
    expect(out).toContain('ingest');
    expect(out).toContain('vault');
  });

  it('paints with explicit fill/stroke attributes (no stylesheet dependency)', () => {
    // The root-cause guard: undefined CSS vars used to make every path paint black.
    expect(out).toContain('fill="#');
    expect(out).toContain('stroke="#');
    expect(out).not.toContain('iso-fill');
    expect(out).not.toContain('var(--anatomy');
  });

  it('sits in a frosted card and is full-viewable', () => {
    expect(out).toContain('be-anatomy');
    expect(out).toContain('glass-card');
    expect(out).toContain('aria-label="View figure full page"');
  });

  it('shows the figure chrome: fig number, legend and caption', () => {
    expect(out).toContain('Fig. 01');
    expect(out).toContain('stored');
    expect(out).toContain('live');
    expect(out).toContain('The refinery, end to end.');
  });

  it('exposes a control for every interaction (play/pause, step, reset)', () => {
    expect(out).toContain('aria-label="Play"');
    expect(out).toContain('aria-label="Next stage"');
    expect(out).toContain('aria-label="Previous stage"');
    expect(out).toContain('aria-label="Reset"');
  });

  it('announces the figure to assistive tech with its description', () => {
    expect(out).toContain('How a market quote flows into the vault and out to the agent.');
  });
});

describe('AnatomyBlock — stages are the only source of live readout', () => {
  it('renders a static readout and NO stage controls when there are no stages', () => {
    const flat = blockOf({ readout: 'steady', parts: [{ id: 'a', w: 20, d: 20, height: 20 }] });
    const out = html(<AnatomyBlock block={flat} />);
    expect(out).toContain('steady');
    expect(out).not.toContain('aria-label="Play"');
    expect(out).not.toContain('aria-label="Next stage"');
  });

  it('summarises the stage count before any stage is selected', () => {
    const out = html(<AnatomyBlock block={figure} />);
    expect(out).toContain('2 stages');
  });

  it('shows an honest empty state rather than a blank figure', () => {
    const empty = blockOf({ title: 'Nothing' });
    const out = html(<AnatomyBlock block={empty} />);
    expect(out).toContain('No parts in this figure.');
  });
});
