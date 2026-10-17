import { describe, it, expect } from 'vitest';
import {
  box,
  boundsOf,
  cylinder,
  extrude,
  gear,
  mergeMeshes,
  revolve,
  transformMesh,
  tube,
} from './mesh';
import { compose, identity } from './math';

const nonEmpty = (mesh: { positions: Float32Array; normals: Float32Array; indices: Uint32Array }) => {
  expect(mesh.positions.length).toBeGreaterThan(0);
  expect(mesh.normals.length).toBe(mesh.positions.length);
  expect(mesh.indices.length).toBeGreaterThan(0);
  expect(mesh.indices.length % 3).toBe(0);
  const maxIndex = Math.max(...mesh.indices);
  expect(maxIndex).toBeLessThan(mesh.positions.length / 3);
};

describe('mesh builders', () => {
  it('box is a closed, indexed cube with finite bounds', () => {
    const mesh = box(20, 10, 30);
    nonEmpty(mesh);
    expect(mesh.indices.length).toBe(36);
    const b = boundsOf(mesh);
    expect(b.min).toEqual([-10, -5, -15]);
    expect(b.max).toEqual([10, 5, 15]);
  });

  it('cylinder/revolve build side and caps', () => {
    nonEmpty(cylinder(5, 12, 24));
    nonEmpty(revolve([[-6, 5], [0, 9], [6, 5]], { segments: 16 }));
  });

  it('extrude triangulates a concave polygon without dropping walls', () => {
    const lShape: Array<[number, number]> = [
      [0, 0], [20, 0], [20, 6], [6, 6], [6, 20], [0, 20],
    ];
    const mesh = extrude(lShape, 4);
    nonEmpty(mesh);
    const b = boundsOf(mesh);
    expect(b.max[2]).toBeCloseTo(2);
    expect(b.min[2]).toBeCloseTo(-2);
  });

  it('gear builds teeth beyond the root radius', () => {
    const mesh = gear(12, 20, 5, 3);
    nonEmpty(mesh);
    const b = boundsOf(mesh);
    expect(Math.max(b.max[0], b.max[1])).toBeGreaterThan(18);
  });

  it('tube sweeps a path and closes a loop', () => {
    nonEmpty(tube([[0, 0, 0], [10, 0, 0], [10, 10, 0]], 1.5));
    nonEmpty(tube([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]], 1.5, { closed: true }));
  });

  it('transformMesh applies rotation and translation to positions and normals', () => {
    const mesh = box(2, 2, 2);
    const moved = transformMesh(mesh, compose([10, 0, 0], [0, 90, 0]));
    const b = boundsOf(moved);
    expect(b.min[0]).toBeCloseTo(9);
    expect(b.max[0]).toBeCloseTo(11);
    // Normals stay unit length after a rigid transform.
    for (let i = 0; i < moved.normals.length; i += 3) {
      expect(Math.hypot(moved.normals[i]!, moved.normals[i + 1]!, moved.normals[i + 2]!)).toBeCloseTo(1, 4);
    }
  });

  it('identity leaves geometry untouched', () => {
    const mesh = cylinder(3, 6, 8);
    const copy = transformMesh(mesh, identity());
    expect(Array.from(copy.positions)).toEqual(Array.from(mesh.positions));
  });

  it('mergeMeshes offsets indices into one buffer', () => {
    const merged = mergeMeshes([box(2, 2, 2), box(2, 2, 2)]);
    nonEmpty(merged);
    expect(Math.max(...merged.indices)).toBe(47);
  });
});
