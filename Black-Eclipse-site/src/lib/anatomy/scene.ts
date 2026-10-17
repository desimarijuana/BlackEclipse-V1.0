// ── Anatomy scene compiler ────────────────────────────────────────────────────
//
// Pure, framework-free (server-safe) glue over the Anatomy-derived kit in this
// directory (see NOTICE). The React renderer only draws what this returns; no
// geometry is computed in a component. It never executes model-authored code: a
// part it cannot place is reported as a diagnostic and simply not drawn.
//
// Part vocabulary — not just boxes and tubes:
//   slab (rounded box) · prism (extruded polygon) · cylinder · disc · knob
//   round, plus TURNED solids from the kit's lathe — lathe (any profile),
//   cone (frustum) and sphere — plus craft decorations (groove, screws, ticks,
//   knurl).

import {
  boxCorners,
  corners,
  cylinder,
  extrude,
  fitProjection,
  insetPlan,
  iso,
  knurl,
  planOutline,
  ring,
  slabOf,
  topMatrix,
  topTicks,
  type Flat,
  type Plane,
  type Point3,
  type Projection,
  type SolidPaths,
} from './iso-kit';
import { frameAlong, solidOf, sphereOf } from './lathe.mjs';
import type { AnatomyBlock } from '@/lib/response/contract';

type AnatomyPart = AnatomyBlock['parts'][number];

const TONES = new Set<string>(['neutral', 'info', 'success', 'warning', 'danger']);
const ROUND = new Set<string>(['cylinder', 'disc', 'knob']);
const TURNED = new Set<string>(['lathe', 'cone', 'sphere']);
const UP: Point3 = [0, 0, 1];

export interface CompiledPart {
  id: string;
  paths: SolidPaths;
  anchor: Flat;
  label?: string;
  labelTransform?: string;
  tone: string;
  lit: boolean;
  halo: boolean;
  overlay?: string;
  overlayStrong?: string;
  dots?: Flat[];
}

export interface CompiledWire {
  from: Flat;
  to: Flat;
  via: Flat[];
  tone: string;
  dotted: boolean;
  dashed: boolean;
  flow: boolean;
}

export interface CompiledAnatomy {
  width: number;
  height: number;
  projection: Projection;
  viewBox: { x: number; y: number; w: number; h: number };
  parts: CompiledPart[];
  wires: CompiledWire[];
  diagnostics: string[];
}

function finite(...values: number[]): boolean {
  return values.every((v) => Number.isFinite(v));
}

interface Geo {
  plan: { x: number; y: number; w: number; d: number; r: number };
  center: [number, number];
  ring?: Plane[];
  profile?: [number, number][];
  radius?: number;
  rTop?: number;
  z0: number;
  z1: number;
  height: number;
}

/** Floor plan + vertical extent + any turned profile for a part, world units. */
function geometryOf(part: AnatomyPart): Geo | null {
  const z = part.z ?? 0;
  const h = part.height ?? (part.kind === 'disc' ? 6 : 16);

  if (part.kind === 'sphere') {
    const r = part.radius ?? 18;
    return { plan: { x: part.x - r, y: part.y - r, w: 2 * r, d: 2 * r, r }, center: [part.x, part.y], radius: r, z0: z, z1: z + 2 * r, height: 2 * r };
  }
  if (part.kind === 'cone') {
    const r0 = part.radius ?? 20;
    const r1 = part.radiusTop ?? 0;
    const rmax = Math.max(r0, r1, 0.001);
    return { plan: { x: part.x - rmax, y: part.y - rmax, w: 2 * rmax, d: 2 * rmax, r: rmax }, center: [part.x, part.y], radius: r0, rTop: r1, z0: z, z1: z + h, height: h };
  }
  if (part.kind === 'lathe') {
    const profile = (part.profile ?? []).map(([s, r]) => [s, Math.max(0, r)] as [number, number]);
    if (profile.length < 2) return null;
    const ss = profile.map(([s]) => s);
    const rs = profile.map(([, r]) => r);
    const sMin = Math.min(...ss);
    const sMax = Math.max(...ss);
    const rmax = Math.max(...rs, 0.001);
    return {
      plan: { x: part.x - rmax, y: part.y - rmax, w: 2 * rmax, d: 2 * rmax, r: rmax },
      center: [part.x, part.y],
      profile,
      radius: rmax,
      z0: z + sMin,
      z1: z + sMax,
      height: sMax - sMin,
    };
  }
  if (ROUND.has(part.kind)) {
    const radius = part.radius ?? 20;
    return { plan: { x: part.x - radius, y: part.y - radius, w: 2 * radius, d: 2 * radius, r: radius }, center: [part.x, part.y], radius, z0: z, z1: z + h, height: h };
  }
  if (part.kind === 'prism' && part.points && part.points.length >= 3) {
    const pts = part.points as [number, number][];
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    const x = Math.min(...xs);
    const y = Math.min(...ys);
    const w = Math.max(...xs) - x || 1;
    const d = Math.max(...ys) - y || 1;
    return { plan: { x, y, w, d, r: 0 }, center: [x + w / 2, y + d / 2], ring: pts, z0: z, z1: z + h, height: h };
  }
  const w = part.w ?? 40;
  const d = part.d ?? 40;
  return { plan: { x: part.x, y: part.y, w, d, r: part.corner ?? 0 }, center: [part.x + w / 2, part.y + d / 2], z0: z, z1: z + h, height: h };
}

export function compileAnatomy(block: AnatomyBlock): CompiledAnatomy {
  const diagnostics: string[] = [];
  const { width, height, azimuth, elevation } = block;

  const placed: Array<{ part: AnatomyPart; geo: Geo }> = [];
  const extremes: Point3[] = [];

  for (const part of block.parts) {
    const geo = geometryOf(part);
    if (!geo) {
      diagnostics.push(`Part "${part.id}" skipped: needs a valid ${part.kind} (profile of 2+ points).`);
      continue;
    }
    if (!finite(part.x, part.y, geo.z0, geo.z1) || geo.z1 <= geo.z0) {
      diagnostics.push(`Part "${part.id}" skipped: non-finite or empty extent.`);
      continue;
    }
    if (geo.plan.w <= 0 || geo.plan.d <= 0) {
      diagnostics.push(`Part "${part.id}" skipped: no footprint.`);
      continue;
    }
    extremes.push(...boxCorners(geo.plan, geo.z0, geo.z1));
    placed.push({ part, geo });
  }

  if (extremes.length === 0) extremes.push([-40, -40, 0], [40, 40, 64]);

  const projection = fitProjection(extremes, width, height, { pad: 32, headroom: 18, azimuth, elevation });

  // Producer order is the painter's order (base/ground first, then parts that
  // stand on it). We do NOT re-sort by depth — a large ground slab's centre sits
  // nearer than a small part resting on its far side.
  const parts: CompiledPart[] = placed.map(({ part, geo }) => {
    const { plan, center, z0, z1 } = geo;
    const radius = geo.radius ?? 20;
    let paths: SolidPaths;

    if (part.kind === 'sphere') {
      paths = sphereOf([center[0], center[1], z0 + radius], radius, projection);
    } else if (part.kind === 'cone') {
      const frame = frameAlong([center[0], center[1], z0], UP);
      paths = solidOf([[0, geo.radius ?? 20], [geo.height, geo.rTop ?? 0]], frame, projection);
    } else if (part.kind === 'lathe' && geo.profile) {
      const frame = frameAlong([center[0], center[1], part.z ?? 0], UP);
      paths = solidOf(geo.profile, frame, projection, part.smooth ? { smooth: true } : {});
    } else if (ROUND.has(part.kind)) {
      paths = cylinder(center[0], center[1], radius, z0, z1 - z0, projection);
    } else if (part.kind === 'prism' && geo.ring) {
      paths = extrude(geo.ring, z0, z1 - z0, projection);
    } else {
      paths = slabOf(plan, z0, z1 - z0, projection);
    }

    const anchor = iso([center[0], center[1], z1], projection);
    const isRoundish = ROUND.has(part.kind) || TURNED.has(part.kind);

    let overlay = '';
    let overlayStrong = '';
    let dots: Flat[] | undefined;

    if (part.groove) {
      overlay += isRoundish
        ? ring(center[0], center[1], radius * 0.78, z1, projection, 40)
        : planOutline(insetPlan(plan, Math.min(plan.w, plan.d) * 0.12), z1, projection);
    }
    if (part.screws && !isRoundish) {
      const inset = Math.min(plan.w, plan.d) * 0.14;
      dots = corners(plan, inset).map(([px, py]) => iso([px, py, z1], projection));
    }
    if (part.knurl && isRoundish) {
      overlay += knurl(center[0], center[1], radius, z0 + 1.5, z1 - 1.5, part.knurlCount ?? 28, projection, 1.4);
    }
    if (part.ticks) {
      const count = typeof part.ticks === 'number' ? part.ticks : part.ticks.count;
      const every = (typeof part.ticks === 'object' && part.ticks.every) || 5;
      const step = plan.w / Math.max(2, count);
      const lengths: [number, number] = [Math.min(3.5, plan.d * 0.16), Math.min(7, plan.d * 0.34)];
      const { minor, major } = topTicks(plan.x, plan.x + plan.w, step, every, plan.y, z1, lengths, projection, 'x');
      overlay += minor;
      overlayStrong += major;
    }

    return {
      id: part.id,
      paths,
      anchor,
      label: part.label,
      labelTransform: part.label ? topMatrix(center, z1, projection) : undefined,
      tone: part.tone,
      lit: part.lit ?? false,
      halo: part.halo ?? false,
      overlay: overlay || undefined,
      overlayStrong: overlayStrong || undefined,
      dots,
    };
  });

  const byId = new Map(parts.map((p) => [p.id, p]));
  const wires: CompiledWire[] = [];
  for (const wire of block.wires) {
    const from = byId.get(wire.from);
    const to = byId.get(wire.to);
    if (!from || !to) {
      diagnostics.push(`Wire ${wire.from}→${wire.to} skipped: endpoint not found.`);
      continue;
    }
    const via: Flat[] = [];
    for (const point of wire.via ?? []) {
      if (point.length < 3 || !finite(point[0], point[1], point[2])) continue;
      via.push(iso([point[0], point[1], point[2]], projection));
    }
    wires.push({
      from: from.anchor,
      to: to.anchor,
      via,
      tone: TONES.has(wire.tone) ? wire.tone : 'neutral',
      dotted: wire.dotted ?? false,
      dashed: wire.dashed ?? false,
      flow: wire.flow ?? false,
    });
  }

  return { width, height, projection, viewBox: tightViewBox(extremes, block, projection), parts, wires, diagnostics };
}

function tightViewBox(extremes: Point3[], block: AnatomyBlock, projection: Projection): { x: number; y: number; w: number; h: number } {
  const points: Flat[] = extremes.map((p) => iso(p, projection));
  for (const wire of block.wires) {
    for (const p of wire.via ?? []) if (p.length === 3 && finite(p[0], p[1], p[2])) points.push(iso([p[0], p[1], p[2]], projection));
  }
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const margin = Math.max(22, Math.max(maxX - minX, maxY - minY) * 0.07);
  return {
    x: Math.round(minX - margin),
    y: Math.round(minY - margin),
    w: Math.round(maxX - minX + margin * 2),
    h: Math.round(maxY - minY + margin * 2),
  };
}
