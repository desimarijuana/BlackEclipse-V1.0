import { describe, it, expect } from 'vitest';
import { model3dBlock } from '@/lib/response/blocks/model3d';
import { compileModel3d } from './compile';
import { model3dToObj, model3dToStl } from './exporters';

function scene() {
  const block = model3dBlock.parse({
    type: 'model3d',
    parts: [{ id: 'b', kind: 'box', w: 20, d: 20, h: 20 }, { id: 'g', recipe: 'gear' }],
  });
  return compileModel3d(block);
}

describe('mesh exporters', () => {
  it('OBJ writes vertices and faces', () => {
    const obj = model3dToObj(scene().parts);
    expect(obj).toMatch(/^v /m);
    expect(obj).toMatch(/^f /m);
    expect(obj).toContain('o eclipse_model');
  });

  it('STL is binary with the correct triangle count', () => {
    const parts = scene().parts;
    const bytes = model3dToStl(parts);
    const triangles = parts.reduce((n, p) => n + p.mesh.indices.length / 3, 0);
    expect(bytes.length).toBe(84 + triangles * 50);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    expect(view.getUint32(80, true)).toBe(triangles);
  });
});
