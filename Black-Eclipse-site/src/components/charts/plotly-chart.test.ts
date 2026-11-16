import { describe, expect, it } from 'vitest';
import { layoutWithSceneOrbit } from './plotly-chart';

describe('layoutWithSceneOrbit', () => {
  it('forces a 3-D scene to orbit even when the flat layout says pan', () => {
    const layout = layoutWithSceneOrbit(
      { dragmode: 'pan', scene: { camera: { eye: { x: 1, y: 2, z: 3 } } } },
      [{ type: 'scatter3d' }],
    );
    expect(layout.dragmode).toBe('pan');
    expect((layout.scene as Record<string, unknown>).dragmode).toBe('turntable');
  });

  it('keeps the camera and the rest of the scene intact', () => {
    const layout = layoutWithSceneOrbit(
      { scene: { aspectmode: 'cube', camera: { eye: { x: 1, y: 2, z: 3 } } } },
      [{ type: 'surface' }],
    );
    const scene = layout.scene as Record<string, unknown>;
    expect(scene.dragmode).toBe('turntable');
    expect(scene.aspectmode).toBe('cube');
    expect(scene.camera).toEqual({ eye: { x: 1, y: 2, z: 3 } });
  });

  it('leaves a 2-D layout alone', () => {
    const layout = { dragmode: 'pan', scene: { dragmode: 'turntable' } };
    expect(layoutWithSceneOrbit(layout, [{ type: 'scatter' }, { type: 'bar' }])).toBe(layout);
  });

  it('handles a missing data array', () => {
    const layout = { dragmode: 'pan' };
    expect(layoutWithSceneOrbit(layout, undefined)).toBe(layout);
  });
});
