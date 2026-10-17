import { describe, it, expect } from 'vitest';
import { compileAnatomy } from './scene';
import { parseResponsePayload, type AnatomyBlock } from '@/lib/response/contract';

// The scene compiler is the Figure's "model": the SINGLE source of truth for
// every drawn part, wire anchor and label transform. These tests pin that it is
// pure, total and deterministic — the property the renderer relies on.

function blockOf(parts: unknown, extra: Record<string, unknown> = {}): AnatomyBlock {
  const parsed = parseResponsePayload({ blocks: [{ type: 'anatomy', parts, ...extra }] });
  const block = parsed.blocks[0];
  if (!block || block.type !== 'anatomy') throw new Error('failed to build an anatomy block');
  return block;
}

const slab = { id: 'vault', kind: 'slab', x: 0, y: 0, w: 40, d: 40, height: 24, label: 'vault' };

describe('compileAnatomy — the deterministic model', () => {
  it('compiles a slab into real, non-empty geometry with a finite projection', () => {
    const scene = compileAnatomy(blockOf([slab]));
    expect(scene.parts).toHaveLength(1);
    expect(scene.parts[0].paths.fill.length).toBeGreaterThan(0);
    expect(scene.parts[0].paths.outline.length).toBeGreaterThan(0);
    expect(scene.parts[0].anchor.every(Number.isFinite)).toBe(true);
    expect(scene.projection.scale).toBeGreaterThan(0);
    expect(scene.diagnostics).toEqual([]);
  });

  it('compiles a cylinder and a rounded slab', () => {
    const scene = compileAnatomy(
      blockOf([
        { id: 'c', kind: 'cylinder', x: 0, y: 0, radius: 20, height: 40 },
        { id: 's', kind: 'slab', x: 60, y: 0, w: 50, d: 30, height: 10, corner: 6 },
      ]),
    );
    expect(scene.parts.map((p) => p.id)).toEqual(['c', 's']);
    expect(scene.parts.every((p) => p.paths.fill.length > 0)).toBe(true);
  });

  it('connects a wire between two known parts and routes waypoints', () => {
    const scene = compileAnatomy(
      blockOf([slab, { id: 'bench', x: 80, y: 0, w: 40, d: 40, height: 20 }], {
        wires: [{ from: 'vault', to: 'bench', via: [[40, 20, 30]], tone: 'success', flow: true }],
      }),
    );
    expect(scene.wires).toHaveLength(1);
    expect(scene.wires[0].tone).toBe('success');
    expect(scene.wires[0].flow).toBe(true);
    expect(scene.wires[0].via).toHaveLength(1);
    expect(scene.wires[0].from.every(Number.isFinite)).toBe(true);
    expect(scene.diagnostics).toEqual([]);
  });

  it('skips a wire whose endpoint is unknown, with a diagnostic (never throws)', () => {
    const scene = compileAnatomy(
      blockOf([slab], { wires: [{ from: 'vault', to: 'ghost' }] }),
    );
    expect(scene.wires).toHaveLength(0);
    expect(scene.diagnostics.some((d) => d.includes('ghost'))).toBe(true);
  });

  it('skips a non-finite part rather than drawing a broken figure', () => {
    // Build a VALIDATED block (so width/height defaults are present), then force
    // one part non-finite to prove the compiler stays total.
    const block = blockOf([
      { id: 'good', w: 20, d: 20, height: 20 },
      { id: 'bad', w: 20, d: 20, height: 20 },
    ]);
    (block.parts[1] as { x: number }).x = Number.NaN;
    const scene = compileAnatomy(block);
    expect(scene.parts.map((p) => p.id)).toEqual(['good']);
    expect(scene.diagnostics.some((d) => d.includes('bad'))).toBe(true);
    expect(scene.projection.scale).toBeGreaterThan(0);
  });

  it('is total for an empty figure — a finite projection, nothing drawn', () => {
    const scene = compileAnatomy(blockOf([]));
    expect(scene.parts).toEqual([]);
    expect(scene.wires).toEqual([]);
    expect(scene.projection.scale).toBeGreaterThan(0);
  });

  it('emits a label transform only when a label is present', () => {
    const withLabel = compileAnatomy(blockOf([slab]));
    const withoutLabel = compileAnatomy(blockOf([{ id: 'x', w: 10, d: 10, height: 10 }]));
    expect(typeof withLabel.parts[0].labelTransform).toBe('string');
    expect(withoutLabel.parts[0].labelTransform).toBeUndefined();
  });

  it('is deterministic — the same block always compiles identically', () => {
    const a = compileAnatomy(blockOf([slab], { stages: [{ label: 'ingest', readout: '3 scrapers' }] }));
    const b = compileAnatomy(blockOf([slab], { stages: [{ label: 'ingest', readout: '3 scrapers' }] }));
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
  });

  it('compiles a prism from a plan polygon', () => {
    const scene = compileAnatomy(blockOf([{ id: 'wedge', kind: 'prism', points: [[0, 0], [40, 0], [40, 30], [0, 30]], height: 20 }]));
    expect(scene.parts[0].paths.fill.length).toBeGreaterThan(0);
  });

  it('adds craft decorations — groove, screws, ticks, knurl', () => {
    const scene = compileAnatomy(
      blockOf([
        { id: 'base', w: 120, d: 80, height: 10, groove: true, screws: true, ticks: { count: 12, every: 4 } },
        { id: 'grip', kind: 'knob', x: 200, radius: 14, height: 20, knurl: true },
      ]),
    );
    const base = scene.parts.find((p) => p.id === 'base')!;
    expect(base.overlay, 'groove + minor ticks').toBeTruthy();
    expect(base.overlayStrong, 'major ticks').toBeTruthy();
    expect(base.dots?.length, 'four corner screws').toBe(4);
    const grip = scene.parts.find((p) => p.id === 'grip')!;
    expect(grip.overlay, 'knurl lines').toBeTruthy();
  });

  it('preserves producer order (base-first painter order)', () => {
    const scene = compileAnatomy(blockOf([
      { id: 'base', w: 100, d: 100, height: 8 },
      { id: 'top', x: 20, y: 20, w: 20, d: 20, z: 8, height: 20 },
    ]));
    expect(scene.parts.map((p) => p.id)).toEqual(['base', 'top']);
  });

  it('compiles turned solids — lathe, cone, sphere', () => {
    const scene = compileAnatomy(blockOf([
      { id: 'bell', kind: 'lathe', x: 0, profile: [[0, 20], [6, 20], [6, 10], [24, 8]], smooth: true },
      { id: 'cone', kind: 'cone', x: 80, radius: 24, radiusTop: 3, height: 40 },
      { id: 'ball', kind: 'sphere', x: 150, radius: 18, z: 20 },
    ]));
    expect(scene.parts.map((p) => p.id)).toEqual(['bell', 'cone', 'ball']);
    expect(scene.parts.every((p) => p.paths.fill.length > 0)).toBe(true);
    expect(scene.diagnostics).toEqual([]);
  });
});
