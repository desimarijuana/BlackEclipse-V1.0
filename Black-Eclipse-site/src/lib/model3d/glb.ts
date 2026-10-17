// ── glTF/GLB export ──────────────────────────────────────────────────────────
//
// A minimal, dependency-free glTF 2.0 binary writer. The compiler has already
// baked world transforms, so every compiled part becomes one mesh node with no
// transform — a genuine 3D asset the user can download and open elsewhere.

import type { CompiledPart } from './compile';
import type { Model3dMaterial } from './names';
import type { Bounds } from './mesh';

// Anatomy parity: exported solids are graphite grey; status `tone` is a viewport
// concept (it colours wires there and does not reach the .glb).
const GRAPHITE: [number, number, number] = [0.58, 0.61, 0.64];

const MATERIALS: Record<Model3dMaterial, { metallic: number; roughness: number; alpha: number }> = {
  metal: { metallic: 0.85, roughness: 0.32, alpha: 1 },
  paint: { metallic: 0.2, roughness: 0.58, alpha: 1 },
  rubber: { metallic: 0, roughness: 0.95, alpha: 1 },
  glass: { metallic: 0.1, roughness: 0.08, alpha: 0.45 },
  plastic: { metallic: 0, roughness: 0.7, alpha: 1 },
  emissive: { metallic: 0, roughness: 0.4, alpha: 1 },
};

function align4(n: number): number {
  return (n + 3) & ~3;
}

function colorOf(material: Model3dMaterial, lit: boolean): [number, number, number] {
  const k = lit ? 1.6 : material === 'metal' ? 1.08 : 1;
  return [
    Math.min(1, GRAPHITE[0] * k),
    Math.min(1, GRAPHITE[1] * k),
    Math.min(1, GRAPHITE[2] * k),
  ];
}

interface Accessor {
  bufferView: number;
  componentType: number;
  count: number;
  type: string;
  min?: number[];
  max?: number[];
}

export function buildGlb(parts: CompiledPart[]): Uint8Array {
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  const bufferViews: Array<{ buffer: number; byteOffset: number; byteLength: number; target?: number }> = [];
  const accessors: Accessor[] = [];
  const materials: Array<Record<string, unknown>> = [];
  const materialIndex = new Map<string, number>();
  const meshes: Array<Record<string, unknown>> = [];
  const nodes: Array<Record<string, unknown>> = [];

  const pushBytes = (bytes: Uint8Array): number => {
    const offset = byteLength;
    chunks.push(bytes);
    byteLength += bytes.length;
    const padding = align4(byteLength) - byteLength;
    if (padding) {
      chunks.push(new Uint8Array(padding));
      byteLength += padding;
    }
    return offset;
  };

  const addView = (bytes: Uint8Array, target?: number): number => {
    const offset = pushBytes(bytes);
    bufferViews.push({ buffer: 0, byteOffset: offset, byteLength: bytes.length, ...(target ? { target } : {}) });
    return bufferViews.length - 1;
  };

  for (const part of parts) {
    const positions = part.mesh.positions;
    const normals = part.mesh.normals;
    const indices = part.mesh.indices;
    if (positions.length === 0 || indices.length === 0) continue;

    const posBytes = new Uint8Array(positions.buffer, positions.byteOffset, positions.byteLength);
    const normBytes = new Uint8Array(normals.buffer, normals.byteOffset, normals.byteLength);
    const idxBytes = new Uint8Array(indices.buffer, indices.byteOffset, indices.byteLength);
    const posView = addView(posBytes, 34962);
    const normView = addView(normBytes, 34962);
    const idxView = addView(idxBytes, 34963);

    const b: Bounds = part.bounds;
    accessors.push({
      bufferView: posView,
      componentType: 5126,
      count: positions.length / 3,
      type: 'VEC3',
      min: [...b.min],
      max: [...b.max],
    });
    accessors.push({
      bufferView: normView,
      componentType: 5126,
      count: normals.length / 3,
      type: 'VEC3',
    });
    accessors.push({
      bufferView: idxView,
      componentType: 5125,
      count: indices.length,
      type: 'SCALAR',
    });
    const posAccessor = accessors.length - 3;
    const normAccessor = accessors.length - 2;
    const idxAccessor = accessors.length - 1;

    const materialKey = `${part.material}:${part.tone}:${part.lit ? 1 : 0}:${part.opacity}`;
    let matIndex = materialIndex.get(materialKey);
    if (matIndex === undefined) {
      const spec = MATERIALS[part.material] ?? MATERIALS.paint;
      const color = colorOf(part.material, part.lit);
      const alpha = Math.min(part.opacity, spec.alpha);
      materials.push({
        name: materialKey,
        pbrMetallicRoughness: {
          baseColorFactor: [color[0], color[1], color[2], alpha],
          metallicFactor: spec.metallic,
          roughnessFactor: spec.roughness,
        },
        doubleSided: true,
        ...(alpha < 1 ? { alphaMode: 'BLEND' } : {}),
      });
      matIndex = materials.length - 1;
      materialIndex.set(materialKey, matIndex);
    }

    meshes.push({
      name: part.id,
      primitives: [
        {
          attributes: { POSITION: posAccessor, NORMAL: normAccessor },
          indices: idxAccessor,
          material: matIndex,
        },
      ],
    });
    nodes.push({ name: part.group, mesh: meshes.length - 1 });
  }

  const json = {
    asset: { version: '2.0', generator: 'BlackEclipse model3d' },
    scene: 0,
    scenes: [{ name: 'Eclipse figure', nodes: nodes.map((_, i) => i) }],
    nodes,
    meshes,
    materials,
    accessors,
    bufferViews,
    buffers: [{ byteLength }],
  };

  const jsonBytes = new TextEncoder().encode(JSON.stringify(json));
  const jsonPadding = align4(jsonBytes.length) - jsonBytes.length;
  const jsonChunk = new Uint8Array(jsonBytes.length + jsonPadding);
  jsonChunk.set(jsonBytes);
  jsonChunk.fill(0x20, jsonBytes.length);

  const bin = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    bin.set(chunk, offset);
    offset += chunk.length;
  }

  const total = 12 + 8 + jsonChunk.length + 8 + bin.length;
  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  view.setUint32(0, 0x46546c67, true); // glTF
  view.setUint32(4, 2, true);
  view.setUint32(8, total, true);
  view.setUint32(12, jsonChunk.length, true);
  view.setUint32(16, 0x4e4f534a, true); // JSON
  out.set(jsonChunk, 20);
  const binHeader = 20 + jsonChunk.length;
  view.setUint32(binHeader, bin.length, true);
  view.setUint32(binHeader + 4, 0x004e4942, true); // BIN
  out.set(bin, binHeader + 8);
  return out;
}
