import { describe, it, expect } from 'vitest';
import { model3dBlock, type Model3dBlock } from '@/lib/response/blocks/model3d';
import { compileModel3d, compileModel3dCached, model3dStats } from './compile';
import { buildGlb } from './glb';
import { RECIPES, RECIPE_PARAM_KEYS } from './recipes';
import { MODEL3D_RECIPES } from './names';

function parse(payload: Record<string, unknown>): Model3dBlock {
  const result = model3dBlock.safeParse({ type: 'model3d', ...payload });
  if (!result.success) throw new Error(JSON.stringify(result.error.issues));
  return result.data;
}

describe('model3d schema ↔ recipe kit', () => {
  it('exposes exactly the recipes the runtime implements', () => {
    expect([...MODEL3D_RECIPES].sort()).toEqual(Object.keys(RECIPES).sort());
  });

  it('declares a parameter contract for every recipe', () => {
    expect(Object.keys(RECIPE_PARAM_KEYS).sort()).toEqual([...MODEL3D_RECIPES].sort());
    for (const keys of Object.values(RECIPE_PARAM_KEYS)) {
      expect(keys.length).toBeGreaterThan(0);
    }
  });

  it('rejects an unknown recipe (never silently degrades)', () => {
    expect(model3dBlock.safeParse({ type: 'model3d', parts: [{ id: 'a', recipe: 'warp-core' }] }).success).toBe(false);
  });

  it('applies camera defaults', () => {
    const block = parse({ parts: [] });
    expect(block.camera.azimuth).toBe(45);
    expect(block.camera.elevation).toBe(28);
    expect(block.ground).toBe(true);
  });
});

describe('compileModel3d — a real scene, deterministically', () => {
  it('compiles a primitive machine and grounds it on z = 0', () => {
    const block = parse({
      camera: { azimuth: 40, elevation: 25 },
      parts: [
        { id: 'base', kind: 'box', w: 60, d: 40, h: 4, position: [0, 0, 60] },
        { id: 'shaft', kind: 'cylinder', radius: 4, h: 30, position: [0, 0, 90], label: 'drive shaft' },
      ],
    });
    const scene = compileModel3d(block);
    expect(scene.diagnostics).toEqual([]);
    expect(scene.parts).toHaveLength(2);
    expect(scene.keys.map((k) => k.id)).toEqual(['shaft']);
    expect(scene.bounds.min[2]).toBeCloseTo(0);
    expect(scene.target[2]).toBeGreaterThan(0);
    expect(scene.distance).toBeGreaterThan(0);
    expect(model3dStats(scene).triangles).toBeGreaterThan(0);
  });

  it('grounds a centred primitive authored at z = 0 (no half-buried parts)', () => {
    const scene = compileModel3d(parse({ parts: [{ id: 'a', kind: 'box', w: 20, d: 20, h: 20 }] }));
    expect(scene.bounds.min[2]).toBeCloseTo(0);
    expect(scene.bounds.max[2]).toBeCloseTo(20);
  });

  it('expands a recipe into a multi-part assembly under one labelled group', () => {
    const block = parse({ parts: [{ id: 'motor1', recipe: 'motor', label: 'drive motor' }] });
    const scene = compileModel3d(block);
    expect(scene.diagnostics).toEqual([]);
    expect(scene.parts.length).toBeGreaterThan(5);
    expect(new Set(scene.parts.map((p) => p.group))).toEqual(new Set(['motor1']));
    expect(scene.keys).toHaveLength(1);
    expect(scene.keys[0]!.label).toBe('drive motor');
  });

  it('reports an unknown recipe parameter instead of silently ignoring it', () => {
    const scene = compileModel3d(parse({ parts: [{ id: 'g', recipe: 'gearbox', params: { width: 50, widht: 10 } }] }));
    expect(scene.diagnostics.some((d) => d.includes('widht'))).toBe(true);
  });

  it('every recipe compiles to renderable geometry', () => {
    for (const name of MODEL3D_RECIPES) {
      const scene = compileModel3d(parse({ parts: [{ id: 'r', recipe: name }] }));
      expect(scene.parts.length, name).toBeGreaterThan(0);
      expect(scene.diagnostics, name).toEqual([]);
    }
  });

  it('composes parent transforms onto children', () => {
    const block = parse({
      parts: [
        { id: 'frame', kind: 'box', w: 40, d: 40, h: 4, position: [0, 0, 0] },
        { id: 'child', kind: 'box', w: 4, d: 4, h: 4, parent: 'frame', position: [100, 0, 10] },
      ],
    });
    const scene = compileModel3d(block);
    const child = scene.parts.find((p) => p.group === 'child')!;
    expect(child.bounds.min[0]).toBeCloseTo(98);
  });

  it('routes wires between known anchors and diagnoses unknown endpoints', () => {
    const block = parse({
      parts: [
        { id: 'a', kind: 'box', position: [0, 0, 0] },
        { id: 'b', kind: 'box', position: [40, 0, 0] },
      ],
      wires: [
        { from: 'a', to: 'b', tone: 'success' },
        { from: 'a', to: 'ghost' },
      ],
    });
    const scene = compileModel3d(block);
    expect(scene.wires).toHaveLength(1);
    expect(scene.diagnostics.some((d) => d.includes('ghost'))).toBe(true);
  });

  it('resolves stage lit sets and exports a stage animation', () => {
    const scene = compileModel3d(
      parse({ parts: [{ id: 'g', recipe: 'gear', lit: true }], stages: [{ label: 'turn', lit: ['g'] }] }),
    );
    expect(scene.stages[0]!.lit).toContain('g');
    const glb = buildGlb(scene.parts, scene.stages);
    const view = new DataView(glb.buffer);
    const jsonLength = view.getUint32(12, true);
    const json = JSON.parse(new TextDecoder().decode(glb.subarray(20, 20 + jsonLength)).trim());
    expect(Array.isArray(json.animations)).toBe(true);
    expect(json.animations[0].channels.length).toBeGreaterThan(0);
  });

  it('is total for an empty scene', () => {
    const scene = compileModel3d(parse({ parts: [] }));
    expect(scene.parts).toEqual([]);
    expect(Number.isFinite(scene.distance)).toBe(true);
    expect(scene.diagnostics.length).toBeGreaterThan(0);
  });

  it('is deterministic — identical input, identical geometry', () => {
    const block = parse({ parts: [{ id: 'g', recipe: 'gearbox', params: { width: 50 } }] });
    const a = compileModel3d(block);
    const b = compileModel3d(block);
    expect(Array.from(a.parts[0]!.mesh.positions)).toEqual(Array.from(b.parts[0]!.mesh.positions));
  });

  it('reuses a cached scene for the same content key', () => {
    const block = parse({ parts: [{ id: 'g', recipe: 'gear' }] });
    const a = compileModel3dCached(block, 'cache-key');
    const b = compileModel3dCached(block, 'cache-key');
    expect(a).toBe(b);
  });
});

describe('buildGlb — a valid glTF binary', () => {
  it('writes a GLB with a JSON chunk naming the parts', () => {
    const scene = compileModel3d(parse({ parts: [{ id: 'pump1', recipe: 'pump', label: 'main pump' }] }));
    const glb = buildGlb(scene.parts);
    const view = new DataView(glb.buffer);
    expect(view.getUint32(0, true)).toBe(0x46546c67);
    expect(view.getUint32(4, true)).toBe(2);
    expect(view.getUint32(8, true)).toBe(glb.length);

    const jsonLength = view.getUint32(12, true);
    const json = new TextDecoder().decode(glb.subarray(20, 20 + jsonLength)).trim();
    const parsed = JSON.parse(json);
    expect(parsed.asset.version).toBe('2.0');
    expect(parsed.meshes.length).toBe(scene.parts.length);
    expect(parsed.meshes.length).toBeGreaterThan(3);
  });
});
