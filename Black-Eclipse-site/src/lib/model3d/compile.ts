// ── model3d scene compiler ───────────────────────────────────────────────────
//
// Pure, framework-free and TOTAL: a declarative scene graph goes in, world-space
// triangle meshes + camera + diagnostics come out. It never throws and never
// executes model-authored code. Geometry it cannot place is reported and skipped.
//
// Pipeline: authored parts → recipes expand into sub-parts → transforms compose
// through parents → every mesh is baked to world space → bounds/camera/grounding.

import type { Model3dBlock, Model3dPart } from '@/lib/response/blocks/model3d';
import {
  box,
  boundsOf,
  cone,
  cylinder,
  emptyMesh,
  extrude,
  gear,
  lathe,
  mergeMeshes,
  sphere,
  torus,
  transformMesh,
  tube,
  type Bounds,
  type Mesh,
} from './mesh';
import { compose, identity, multiply, type Mat4, type Vec3 } from './math';
import { RECIPES, type RecipePart } from './recipes';
import type { Model3dMaterial, Model3dTone } from './names';

export interface CompiledPart {
  /** Unique render id (recipe sub-parts use `group~n`). */
  id: string;
  /** The authored part id (the unit a label/stage/wire refers to). */
  group: string;
  mesh: Mesh;
  tone: Model3dTone;
  material: Model3dMaterial;
  opacity: number;
  lit: boolean;
  anchor: Vec3;
  bounds: Bounds;
}

export interface CompiledKey {
  id: string;
  label: string;
  anchor: Vec3;
}

export interface CompiledWire {
  from: Vec3;
  to: Vec3;
  tone: Model3dTone;
  dashed: boolean;
  dotted: boolean;
  label?: string;
}

export interface CompiledModel3d {
  width: number;
  height: number;
  parts: CompiledPart[];
  keys: CompiledKey[];
  wires: CompiledWire[];
  bounds: Bounds;
  target: Vec3;
  distance: number;
  azimuth: number;
  elevation: number;
  diagnostics: string[];
}

const FOV = 35;

function geometryOf(spec: {
  kind: Model3dPart['kind'];
  w?: number;
  d?: number;
  h?: number;
  radius?: number;
  radiusTop?: number;
  tube?: number;
  points?: Array<[number, number]>;
  profile?: Array<[number, number]>;
  path?: Vec3[];
  closed?: boolean;
  teeth?: number;
  toothDepth?: number;
}): Mesh | null {
  switch (spec.kind) {
    case 'box':
      return box(spec.w ?? 20, spec.d ?? 20, spec.h ?? 20);
    case 'cylinder':
      return cylinder(spec.radius ?? 10, spec.h ?? 20);
    case 'cone':
      return cone(spec.radius ?? 10, spec.radiusTop ?? 0, spec.h ?? 20);
    case 'sphere':
      return sphere(spec.radius ?? 10);
    case 'torus':
      return torus(spec.radius ?? 16, spec.tube ?? 4);
    case 'lathe':
      return spec.profile && spec.profile.length >= 2 ? lathe(spec.profile) : null;
    case 'extrude':
      return spec.points && spec.points.length >= 3 ? extrude(spec.points, spec.h ?? 20) : null;
    case 'tube':
      return spec.path && spec.path.length >= 2
        ? tube(spec.path, spec.tube ?? 2, { closed: spec.closed })
        : null;
    case 'gear': {
      const radius = spec.radius ?? 20;
      return gear(spec.teeth ?? 18, radius, spec.h ?? 6, spec.toothDepth ?? radius * 0.16);
    }
    default:
      return null;
  }
}

function localMatrix(spec: {
  position?: Vec3;
  rotation?: Vec3;
  scale?: Vec3;
}): Mat4 {
  return compose(spec.position ?? [0, 0, 0], spec.rotation ?? [0, 0, 0], spec.scale ?? [1, 1, 1]);
}

function emptyBounds(): Bounds {
  return { min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity] };
}

function grow(bounds: Bounds, other: Bounds): void {
  for (let i = 0; i < 3; i++) {
    bounds.min[i] = Math.min(bounds.min[i]!, other.min[i]!);
    bounds.max[i] = Math.max(bounds.max[i]!, other.max[i]!);
  }
}

function validBounds(bounds: Bounds): boolean {
  return Number.isFinite(bounds.min[0]) && bounds.max[0]! >= bounds.min[0]!;
}

function anchorOf(bounds: Bounds): Vec3 {
  return [
    (bounds.min[0]! + bounds.max[0]!) / 2,
    (bounds.min[1]! + bounds.max[1]!) / 2,
    bounds.max[2]!,
  ];
}

function shiftMesh(mesh: Mesh, dz: number): Mesh {
  if (!dz) return mesh;
  const positions = new Float32Array(mesh.positions);
  for (let i = 2; i < positions.length; i += 3) positions[i] = positions[i]! + dz;
  return { ...mesh, positions };
}

export function compileModel3d(block: Model3dBlock): CompiledModel3d {
  const diagnostics: string[] = [];
  const byId = new Map<string, Model3dPart>();
  for (const part of block.parts) {
    if (byId.has(part.id)) diagnostics.push(`Part "${part.id}" is duplicated; the later one wins.`);
    byId.set(part.id, part);
  }

  const worldCache = new Map<string, Mat4>();
  const resolving = new Set<string>();

  const worldOf = (part: Model3dPart): Mat4 => {
    const cached = worldCache.get(part.id);
    if (cached) return cached;
    if (resolving.has(part.id)) {
      diagnostics.push(`Part "${part.id}" has a parent cycle; it is placed at the root.`);
      return localMatrix(part);
    }
    resolving.add(part.id);
    const local = localMatrix(part);
    const parent = part.parent ? byId.get(part.parent) : undefined;
    if (part.parent && !parent) diagnostics.push(`Part "${part.id}" has unknown parent "${part.parent}".`);
    const world = parent && parent !== part ? multiply(worldOf(parent), local) : local;
    resolving.delete(part.id);
    worldCache.set(part.id, world);
    return world;
  };

  const parts: CompiledPart[] = [];
  const keys: CompiledKey[] = [];
  const groupAnchors = new Map<string, Vec3>();
  const total = emptyBounds();

  const push = (
    group: string,
    id: string,
    mesh: Mesh,
    material: Model3dMaterial,
    tone: Model3dTone,
    opacity: number,
    lit: boolean,
  ): void => {
    const bounds = boundsOf(mesh);
    if (!validBounds(bounds) || mesh.indices.length === 0) {
      diagnostics.push(`Part "${group}" skipped: empty geometry.`);
      return;
    }
    parts.push({ id, group, mesh, tone, material, opacity, lit, anchor: anchorOf(bounds), bounds });
    grow(total, bounds);
  };

  for (const part of block.parts) {
    const world = worldOf(part);
    if (part.recipe) {
      const recipe = RECIPES[part.recipe];
      if (!recipe) {
        diagnostics.push(`Part "${part.id}" skipped: unknown recipe "${part.recipe}".`);
        continue;
      }
      const recipeParts: RecipePart[] = recipe(part.params ?? {});
      const groupBounds = emptyBounds();
      let made = 0;
      recipeParts.forEach((spec, index) => {
        const mesh = geometryOf(spec);
        if (!mesh) {
          diagnostics.push(`Recipe "${part.recipe}" part ${index} has invalid geometry.`);
          return;
        }
        const baked = transformMesh(mesh, multiply(world, localMatrix(spec)));
        const bounds = boundsOf(baked);
        if (!validBounds(bounds) || baked.indices.length === 0) return;
        grow(groupBounds, bounds);
        made++;
        parts.push({
          id: `${part.id}~${index}`,
          group: part.id,
          mesh: baked,
          tone: spec.tone ?? part.tone,
          material: spec.material ?? part.material,
          opacity: part.opacity,
          lit: spec.lit ?? part.lit ?? false,
          anchor: anchorOf(bounds),
          bounds,
        });
      });
      if (made > 0) {
        grow(total, groupBounds);
        const anchor = anchorOf(groupBounds);
        groupAnchors.set(part.id, anchor);
        if (part.label) keys.push({ id: part.id, label: part.label, anchor });
      }
      continue;
    }

    const mesh = geometryOf(part);
    if (!mesh) {
      diagnostics.push(`Part "${part.id}" skipped: invalid ${part.kind} geometry.`);
      continue;
    }
    const baked = transformMesh(mesh, world);
    const before = parts.length;
    push(part.id, part.id, baked, part.material, part.tone, part.opacity, part.lit ?? false);
    if (parts.length > before) {
      const anchor = parts[parts.length - 1]!.anchor;
      groupAnchors.set(part.id, anchor);
      if (part.label) keys.push({ id: part.id, label: part.label, anchor });
    }
  }

  // Ground the whole scene: drop it onto z = 0. This lifts a floating machine and
  // also raises centred primitives authored at z = 0, which would otherwise sink
  // half-way through the ground plane. `ground: false` opts out.
  if (block.ground && validBounds(total) && Math.abs(total.min[2]!) > 0.01) {
    const dz = -total.min[2]!;
    for (const part of parts) {
      part.mesh = shiftMesh(part.mesh, dz);
      part.bounds = { min: [part.bounds.min[0], part.bounds.min[1], part.bounds.min[2] + dz], max: [part.bounds.max[0], part.bounds.max[1], part.bounds.max[2] + dz] };
      part.anchor = [part.anchor[0], part.anchor[1], part.anchor[2] + dz];
    }
    for (const key of keys) key.anchor = [key.anchor[0], key.anchor[1], key.anchor[2] + dz];
    for (const [id, anchor] of groupAnchors) groupAnchors.set(id, [anchor[0], anchor[1], anchor[2] + dz]);
    total.min[2] = 0;
    total.max[2] = total.max[2]! + dz;
  }

  if (parts.length === 0) diagnostics.push('This model has no renderable parts.');

  const wires: CompiledWire[] = [];
  for (const wire of block.wires) {
    const from = groupAnchors.get(wire.from);
    const to = groupAnchors.get(wire.to);
    if (!from || !to) {
      diagnostics.push(`Wire ${wire.from}→${wire.to} skipped: endpoint not found.`);
      continue;
    }
    wires.push({
      from,
      to,
      tone: wire.tone,
      dashed: wire.dashed === true,
      dotted: wire.dotted === true,
      label: wire.label,
    });
  }

  const bounds = validBounds(total) ? total : { min: [-20, -20, 0] as Vec3, max: [20, 20, 20] as Vec3 };
  const target: Vec3 = block.camera.target ?? [
    (bounds.min[0] + bounds.max[0]) / 2,
    (bounds.min[1] + bounds.max[1]) / 2,
    (bounds.min[2] + bounds.max[2]) / 2,
  ];
  const extent = Math.max(
    bounds.max[0] - bounds.min[0],
    bounds.max[1] - bounds.min[1],
    bounds.max[2] - bounds.min[2],
    10,
  );
  const distance =
    block.camera.distance ??
    (extent / (2 * Math.tan((FOV * Math.PI) / 360))) * 1.45;

  return {
    width: block.width,
    height: block.height,
    parts,
    keys,
    wires,
    bounds,
    target,
    distance,
    azimuth: block.camera.azimuth,
    elevation: block.camera.elevation,
    diagnostics,
  };
}

/** Total scene stats, used by the block summary and tests. */
export function model3dStats(scene: CompiledModel3d): { parts: number; triangles: number } {
  let triangles = 0;
  for (const part of scene.parts) triangles += part.mesh.indices.length / 3;
  return { parts: scene.parts.length, triangles };
}

export { emptyMesh, mergeMeshes, identity };
