// ── glTF/GLB export ──────────────────────────────────────────────────────────
//
// A minimal, dependency-free glTF 2.0 binary writer. The compiler has already
// baked world transforms, so every compiled part becomes one mesh node with no
// transform — a genuine 3D asset the user can download and open elsewhere.

import type { CompiledPart } from './compile';
import type { Model3dMaterial } from './names';
import type { Bounds } from './mesh';

// Flat sketch parity with the viewport: solids fill with the paper colour
// (#161618) and are read by #3A3E44 outline LINES exported alongside them.
const PAPER: [number, number, number] = [0.086, 0.086, 0.094]; // #161618
const OUTLINE_COLOR: [number, number, number] = [0.227, 0.243, 0.267]; // #3A3E44

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

function colorOf(lit: boolean): [number, number, number] {
  return lit ? [0.13, 0.14, 0.15] : PAPER;
}

interface Accessor {
  bufferView: number;
  componentType: number;
  count: number;
  type: string;
  min?: number[];
  max?: number[];
}

export function buildGlb(
  parts: CompiledPart[],
  stages: Array<{ label: string; lit: string[] }> = [],
): Uint8Array {
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  const bufferViews: Array<{ buffer: number; byteOffset: number; byteLength: number; target?: number }> = [];
  const accessors: Accessor[] = [];
  const materials: Array<Record<string, unknown>> = [];
  const materialIndex = new Map<string, number>();
  const meshes: Array<Record<string, unknown>> = [];
  const nodes: Array<Record<string, unknown>> = [];
  let outlineMat: number | null = null;
  // For the stage animation: which node indices + baked centre belong to a group.
  const groupNodes = new Map<string, number[]>();
  const groupCenter = new Map<string, [number, number, number, number]>();

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
      const color = colorOf(part.lit);
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

    const primitives: Array<Record<string, unknown>> = [
      {
        attributes: { POSITION: posAccessor, NORMAL: normAccessor },
        indices: idxAccessor,
        material: matIndex,
      },
    ];

    // Outline LINES (part.edges) share the part node so the drawing travels with
    // the model. One shared outline material keeps the file small.
    if (part.edges.length >= 6) {
      if (outlineMat === null) {
        materials.push({
          name: 'outline',
          pbrMetallicRoughness: {
            baseColorFactor: [OUTLINE_COLOR[0], OUTLINE_COLOR[1], OUTLINE_COLOR[2], 1],
            metallicFactor: 0,
            roughnessFactor: 1,
          },
        });
        outlineMat = materials.length - 1;
      }
      const edgeBytes = new Uint8Array(part.edges.buffer, part.edges.byteOffset, part.edges.byteLength);
      const edgeView = addView(edgeBytes, 34962);
      accessors.push({ bufferView: edgeView, componentType: 5126, count: part.edges.length / 3, type: 'VEC3' });
      primitives.push({
        attributes: { POSITION: accessors.length - 1 },
        mode: 1,
        material: outlineMat,
      });
    }

    meshes.push({ name: part.id, primitives });
    nodes.push({ name: part.group, mesh: meshes.length - 1 });
    const nodeIndex = nodes.length - 1;
    const list = groupNodes.get(part.group);
    if (list) list.push(nodeIndex);
    else groupNodes.set(part.group, [nodeIndex]);
    const c = groupCenter.get(part.group) ?? [0, 0, 0, 0];
    c[0] += (part.bounds.min[0] + part.bounds.max[0]) / 2;
    c[1] += (part.bounds.min[1] + part.bounds.max[1]) / 2;
    c[2] += (part.bounds.min[2] + part.bounds.max[2]) / 2;
    c[3] += 1;
    groupCenter.set(part.group, c);
  }

  // Stage animation: each stage pulses its lit groups. Geometry is baked, so a
  // group is scaled about its own centre by pairing `scale` with a compensating
  // `translation` (t = c·(1−k)) — a pivot-correct animation with no extra graph.
  const animations: Array<Record<string, unknown>> = [];
  if (stages.length > 0 && groupNodes.size > 0) {
    const samples = stages.length + 1;
    const times = new Float32Array(samples);
    for (let i = 0; i < samples; i++) times[i] = i;
    const timeAccessor = accessors.length;
    accessors.push({
      bufferView: addView(new Uint8Array(times.buffer, times.byteOffset, times.byteLength)),
      componentType: 5126,
      count: samples,
      type: 'SCALAR',
      min: [0],
      max: [samples - 1],
    });

    const samplers: Array<Record<string, unknown>> = [];
    const channels: Array<Record<string, unknown>> = [];
    for (const [group, indices] of groupNodes) {
      const c = groupCenter.get(group);
      if (!c || c[3] === 0) continue;
      const cx = c[0] / c[3], cy = c[1] / c[3], cz = c[2] / c[3];
      const scale = new Float32Array(samples * 3);
      const trans = new Float32Array(samples * 3);
      for (let s = 0; s < samples; s++) {
        const lit = s > 0 && stages[s - 1]!.lit.includes(group);
        const k = lit ? 1.08 : 1;
        scale[s * 3] = k; scale[s * 3 + 1] = k; scale[s * 3 + 2] = k;
        trans[s * 3] = cx * (1 - k); trans[s * 3 + 1] = cy * (1 - k); trans[s * 3 + 2] = cz * (1 - k);
      }
      const scaleAccessor = accessors.length;
      accessors.push({ bufferView: addView(new Uint8Array(scale.buffer, scale.byteOffset, scale.byteLength)), componentType: 5126, count: samples, type: 'VEC3' });
      const transAccessor = accessors.length;
      accessors.push({ bufferView: addView(new Uint8Array(trans.buffer, trans.byteOffset, trans.byteLength)), componentType: 5126, count: samples, type: 'VEC3' });
      const scaleSampler = samplers.length;
      samplers.push({ input: timeAccessor, output: scaleAccessor, interpolation: 'LINEAR' });
      const transSampler = samplers.length;
      samplers.push({ input: timeAccessor, output: transAccessor, interpolation: 'LINEAR' });
      for (const node of indices) {
        channels.push({ sampler: scaleSampler, target: { node, path: 'scale' } });
        channels.push({ sampler: transSampler, target: { node, path: 'translation' } });
      }
    }
    animations.push({ name: 'stages', samplers, channels });
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
    ...(animations.length ? { animations } : {}),
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
