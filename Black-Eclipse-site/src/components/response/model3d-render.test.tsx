// ── Model3dBlock render + affordance tests (server-rendered) ──────────────────
//
// The WebGL viewport is client-only (next/dynamic ssr:false), so this locks in
// the parts that MUST survive without it: the numbered key, legend, readout,
// stages controls and the GLB download affordance. If the DOM half regressed,
// the model would be an empty canvas with no accessible fallback.

import { describe, it, expect } from 'vitest';
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseResponsePayload, type Model3dBlock as Model3dBlockType } from '@/lib/response/contract';
import { Model3dBlock } from './model3d-block';

const html = (node: ReactElement): string => renderToStaticMarkup(node);

function blockOf(payload: Record<string, unknown>): Model3dBlockType {
  const block = parseResponsePayload({ blocks: [{ type: 'model3d', ...payload }] }).blocks[0];
  if (!block || block.type !== 'model3d') throw new Error('failed to build a model3d block');
  return block;
}

const figure = blockOf({
  title: 'Order matching engine',
  fig: 'Fig. 3D',
  description: 'A gearbox that pairs incoming orders.',
  caption: 'The matching core.',
  readout: 'idle',
  legend: [{ label: 'flow', mark: 'blue' }],
  parts: [
    { id: 'base', recipe: 'frame', label: 'mounting frame' },
    { id: 'core', recipe: 'gearbox', lit: true, label: 'matching gearbox' },
  ],
  wires: [{ from: 'base', to: 'core', tone: 'info' }],
  stages: [
    { label: 'ingest', note: 'orders arrive', readout: 'matching', lit: ['core'] },
    { label: 'settle', readout: 'settled', lit: ['base'] },
  ],
});

describe('Model3dBlock — a model, not just a canvas', () => {
  const out = html(<Model3dBlock block={figure} />);

  it('renders the titled card with its numbered key', () => {
    expect(out).toContain('Order matching engine');
    expect(out).toContain('mounting frame');
    expect(out).toContain('matching gearbox');
    expect(out).toContain('drag to orbit');
  });

  it('exposes the GLB download and stage affordances', () => {
    expect(out).toContain('Download .glb');
    expect(out.toLowerCase()).toContain('previous stage');
    expect(out.toLowerCase()).toContain('next stage');
  });

  it('shows the legend and readout', () => {
    expect(out).toContain('flow');
    expect(out).toContain('idle');
  });

  it('is total for an empty model (no crash, honest message)', () => {
    const empty = html(<Model3dBlock block={blockOf({ parts: [] })} />);
    expect(empty).toContain('No parts in this model.');
  });
});
