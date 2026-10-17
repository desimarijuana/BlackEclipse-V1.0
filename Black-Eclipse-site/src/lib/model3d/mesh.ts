// ── Triangle mesh builders ────────────────────────────────────────────────────
//
// Pure, framework-free geometry. Every builder returns indexed triangles in
// metres-like world units, centred on the part origin, Z up. The compile step
// bakes transforms; the renderer and the GLB writer consume these buffers
// directly, so there is exactly ONE geometry implementation.

import {
  add,
  cross,
  dot,
  normalize,
  scale as vscale,
  sub,
  transformPoint,
  normalMatrix,
  applyNormal,
  type Mat4,
  type Vec3,
} from './math';

export interface Mesh {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
}

export interface Bounds {
  min: Vec3;
  max: Vec3;
}

class Builder {
  positions: number[] = [];
  normals: number[] = [];
  indices: number[] = [];

  vertex(p: Vec3, n: Vec3): number {
    this.positions.push(p[0], p[1], p[2]);
    this.normals.push(n[0], n[1], n[2]);
    return this.positions.length / 3 - 1;
  }

  tri(a: number, b: number, c: number): void {
    this.indices.push(a, b, c);
  }

  quad(a: number, b: number, c: number, d: number): void {
    this.indices.push(a, b, c, a, c, d);
  }

  build(): Mesh {
    return {
      positions: new Float32Array(this.positions),
      normals: new Float32Array(this.normals),
      indices: new Uint32Array(this.indices),
    };
  }
}

const TAU = Math.PI * 2;
const rad = (a: number): number => (a * Math.PI) / 180;

export function emptyMesh(): Mesh {
  return { positions: new Float32Array(0), normals: new Float32Array(0), indices: new Uint32Array(0) };
}

export function boundsOf(mesh: Mesh): Bounds {
  const min: Vec3 = [Infinity, Infinity, Infinity];
  const max: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < mesh.positions.length; i += 3) {
    for (let k = 0; k < 3; k++) {
      const v = mesh.positions[i + k]!;
      if (v < min[k]!) min[k] = v;
      if (v > max[k]!) max[k] = v;
    }
  }
  if (!Number.isFinite(min[0])) return { min: [0, 0, 0], max: [0, 0, 0] };
  return { min, max };
}

export function transformMesh(mesh: Mesh, m: Mat4): Mesh {
  const out = new Builder();
  const nm = normalMatrix(m);
  for (let i = 0; i < mesh.positions.length; i += 3) {
    const p = transformPoint(m, [mesh.positions[i]!, mesh.positions[i + 1]!, mesh.positions[i + 2]!]);
    const n = applyNormal(nm, [mesh.normals[i]!, mesh.normals[i + 1]!, mesh.normals[i + 2]!]);
    out.vertex(p, n);
  }
  out.indices = Array.from(mesh.indices);
  return out.build();
}

export function mergeMeshes(meshes: Mesh[]): Mesh {
  const out = new Builder();
  for (const mesh of meshes) {
    const base = out.positions.length / 3;
    out.positions.push(...mesh.positions);
    out.normals.push(...mesh.normals);
    for (const index of mesh.indices) out.indices.push(index + base);
  }
  return out.build();
}

// ── Box ──────────────────────────────────────────────────────────────────────

export function box(w = 20, d = 20, h = 20): Mesh {
  const x = w / 2, y = d / 2, z = h / 2;
  const b = new Builder();
  const face = (corners: Vec3[], n: Vec3) => {
    const ids = corners.map((p) => b.vertex(p, n));
    b.quad(ids[0]!, ids[1]!, ids[2]!, ids[3]!);
  };
  face([[-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z]], [0, 0, 1]);
  face([[-x, y, -z], [x, y, -z], [x, -y, -z], [-x, -y, -z]], [0, 0, -1]);
  face([[x, -y, -z], [x, y, -z], [x, y, z], [x, -y, z]], [1, 0, 0]);
  face([[-x, -y, z], [-x, y, z], [-x, y, -z], [-x, -y, -z]], [-1, 0, 0]);
  face([[-x, y, -z], [-x, y, z], [x, y, z], [x, y, -z]], [0, 1, 0]);
  face([[x, -y, -z], [x, -y, z], [-x, -y, z], [-x, -y, -z]], [0, -1, 0]);
  return b.build();
}

// ── Revolve (cylinder, cone, lathe) ─────────────────────────────────────────

export interface RevolveOptions {
  segments?: number;
  /** Skip caps (open shell, e.g. a pipe). */
  open?: boolean;
}

/** Revolve a `[z, radius]` profile around the Z axis. */
export function revolve(profile: Array<[number, number]>, options: RevolveOptions = {}): Mesh {
  const seg = Math.max(8, Math.min(96, options.segments ?? 48));
  const pts = profile.filter(([, r]) => Number.isFinite(r) && r >= 0);
  if (pts.length < 2) return emptyMesh();
  const b = new Builder();

  // Side surface, smooth normals from the profile tangent.
  const rings: number[][] = [];
  for (let i = 0; i < pts.length; i++) {
    const [z, r] = pts[i]!;
    const prev = pts[Math.max(0, i - 1)]!;
    const next = pts[Math.min(pts.length - 1, i + 1)]!;
    const dz = next[0] - prev[0] || 1;
    const dr = next[1] - prev[1];
    const ring: number[] = [];
    for (let s = 0; s <= seg; s++) {
      const a = (s / seg) * TAU;
      const c = Math.cos(a), sn = Math.sin(a);
      ring.push(b.vertex([r * c, r * sn, z], normalize([dz * c, dz * sn, -dr])));
    }
    rings.push(ring);
  }
  for (let i = 0; i < rings.length - 1; i++) {
    for (let s = 0; s < seg; s++) {
      b.quad(rings[i]![s]!, rings[i]![s + 1]!, rings[i + 1]![s + 1]!, rings[i + 1]![s]!);
    }
  }

  if (!options.open) {
    // Caps at non-zero-radius ends (a zero-radius end is already closed).
    const cap = (index: number, at: 'start' | 'end') => {
      const [z, r] = pts[index]!;
      if (r <= 1e-6) return;
      const up = at === 'end' ? 1 : -1;
      const center = b.vertex([0, 0, z], [0, 0, up]);
      const ring: number[] = [];
      for (let s = 0; s <= seg; s++) {
        const a = (s / seg) * TAU;
        ring.push(b.vertex([r * Math.cos(a), r * Math.sin(a), z], [0, 0, up]));
      }
      for (let s = 0; s < seg; s++) {
        if (up > 0) b.tri(center, ring[s]!, ring[s + 1]!);
        else b.tri(center, ring[s + 1]!, ring[s]!);
      }
    };
    cap(0, 'start');
    cap(pts.length - 1, 'end');
  }

  return b.build();
}

export function cylinder(radius = 10, h = 20, segments = 48): Mesh {
  return revolve([[-h / 2, radius], [h / 2, radius]], { segments });
}

export function cone(radiusBottom = 10, radiusTop = 0, h = 20, segments = 48): Mesh {
  return revolve([[-h / 2, radiusBottom], [h / 2, radiusTop]], { segments });
}

export function lathe(profile: Array<[number, number]>, segments = 48): Mesh {
  return revolve(profile, { segments });
}

// ── Sphere ───────────────────────────────────────────────────────────────────

export function sphere(radius = 10, widthSegments = 32, heightSegments = 20): Mesh {
  const b = new Builder();
  const grid: number[][] = [];
  for (let y = 0; y <= heightSegments; y++) {
    const v = y / heightSegments;
    const phi = v * Math.PI;
    const row: number[] = [];
    for (let x = 0; x <= widthSegments; x++) {
      const u = x / widthSegments;
      const theta = u * TAU;
      const n: Vec3 = [
        Math.sin(phi) * Math.cos(theta),
        Math.sin(phi) * Math.sin(theta),
        Math.cos(phi),
      ];
      row.push(b.vertex(vscale(n, radius), n));
    }
    grid.push(row);
  }
  for (let y = 0; y < heightSegments; y++) {
    for (let x = 0; x < widthSegments; x++) {
      const a = grid[y]![x]!, bb = grid[y]![x + 1]!;
      const c = grid[y + 1]![x + 1]!, d = grid[y + 1]![x]!;
      b.quad(a, bb, c, d);
    }
  }
  return b.build();
}

// ── Torus ────────────────────────────────────────────────────────────────────

export function torus(radius = 16, tube = 4, radialSegments = 18, tubularSegments = 48): Mesh {
  const R = Math.max(tube, radius);
  const r = Math.min(tube, R * 0.9);
  const b = new Builder();
  const grid: number[][] = [];
  for (let i = 0; i <= tubularSegments; i++) {
    const u = (i / tubularSegments) * TAU;
    const row: number[] = [];
    for (let j = 0; j <= radialSegments; j++) {
      const v = (j / radialSegments) * TAU;
      const n: Vec3 = [Math.cos(v) * Math.cos(u), Math.cos(v) * Math.sin(u), Math.sin(v)];
      row.push(
        b.vertex(
          [(R + r * Math.cos(v)) * Math.cos(u), (R + r * Math.cos(v)) * Math.sin(u), r * Math.sin(v)],
          n,
        ),
      );
    }
    grid.push(row);
  }
  for (let i = 0; i < tubularSegments; i++) {
    for (let j = 0; j < radialSegments; j++) {
      b.quad(grid[i]![j]!, grid[i + 1]![j]!, grid[i + 1]![j + 1]!, grid[i]![j + 1]!);
    }
  }
  return b.build();
}

// ── Extrude a 2D polygon ─────────────────────────────────────────────────────

function signedArea(points: Array<[number, number]>): number {
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const [ax, ay] = points[i]!;
    const [bx, by] = points[(i + 1) % points.length]!;
    area += ax * by - bx * ay;
  }
  return area / 2;
}

/** Ear clipping; total for simple polygons, degrades to a fan when no ear is found. */
function triangulate(points: Array<[number, number]>): Array<[number, number, number]> {
  const n = points.length;
  if (n < 3) return [];
  const indices = points.map((_, i) => i);
  const out: Array<[number, number, number]> = [];
  const cross2 = (a: [number, number], b: [number, number], c: [number, number]) =>
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const inside = (p: [number, number], a: [number, number], b: [number, number], c: [number, number]) => {
    const d1 = cross2(a, b, p), d2 = cross2(b, c, p), d3 = cross2(c, a, p);
    return d1 >= 0 && d2 >= 0 && d3 >= 0;
  };
  let guard = n * n;
  while (indices.length > 3 && guard-- > 0) {
    let clipped = false;
    for (let i = 0; i < indices.length; i++) {
      const i0 = indices[(i + indices.length - 1) % indices.length]!;
      const i1 = indices[i]!;
      const i2 = indices[(i + 1) % indices.length]!;
      if (cross2(points[i0]!, points[i1]!, points[i2]!) <= 0) continue;
      let blocked = false;
      for (const j of indices) {
        if (j === i0 || j === i1 || j === i2) continue;
        if (inside(points[j]!, points[i0]!, points[i1]!, points[i2]!)) { blocked = true; break; }
      }
      if (blocked) continue;
      out.push([i0, i1, i2]);
      indices.splice(i, 1);
      clipped = true;
      break;
    }
    if (!clipped) break;
  }
  if (indices.length === 3) out.push([indices[0]!, indices[1]!, indices[2]!]);
  return out;
}

export function extrude(points: Array<[number, number]>, h = 20): Mesh {
  let poly = points.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if (poly.length < 3) return emptyMesh();
  if (signedArea(poly) < 0) poly = [...poly].reverse();
  const z = h / 2;
  const b = new Builder();
  const tris = triangulate(poly);

  for (const [i0, i1, i2] of tris) {
    const p0 = poly[i0]!, p1 = poly[i1]!, p2 = poly[i2]!;
    const a = b.vertex([p0[0], p0[1], z], [0, 0, 1]);
    const c = b.vertex([p1[0], p1[1], z], [0, 0, 1]);
    const d = b.vertex([p2[0], p2[1], z], [0, 0, 1]);
    b.tri(a, c, d);
    const e = b.vertex([p0[0], p0[1], -z], [0, 0, -1]);
    const f = b.vertex([p1[0], p1[1], -z], [0, 0, -1]);
    const g = b.vertex([p2[0], p2[1], -z], [0, 0, -1]);
    b.tri(e, g, f);
  }

  for (let i = 0; i < poly.length; i++) {
    const p0 = poly[i]!, p1 = poly[(i + 1) % poly.length]!;
    const dx = p1[0] - p0[0], dy = p1[1] - p0[1];
    const len = Math.hypot(dx, dy) || 1;
    const n: Vec3 = [dy / len, -dx / len, 0];
    const a = b.vertex([p0[0], p0[1], -z], n);
    const c = b.vertex([p1[0], p1[1], -z], n);
    const d = b.vertex([p1[0], p1[1], z], n);
    const e = b.vertex([p0[0], p0[1], z], n);
    b.quad(a, c, d, e);
  }

  return b.build();
}

// ── Tube (sweep along a centreline) ──────────────────────────────────────────

export function tube(path: Vec3[], radius = 3, options: { radialSegments?: number; closed?: boolean } = {}): Mesh {
  const pts = path.filter((p) => p.every(Number.isFinite));
  if (pts.length < 2) return emptyMesh();
  const closed = options.closed === true;
  const radial = Math.max(6, Math.min(32, options.radialSegments ?? 14));
  const b = new Builder();

  const tangentAt = (i: number): Vec3 => {
    if (closed) return normalize(sub(pts[(i + 1) % pts.length]!, pts[(i - 1 + pts.length) % pts.length]!));
    const a = pts[Math.max(0, i - 1)]!, c = pts[Math.min(pts.length - 1, i + 1)]!;
    return normalize(sub(c, a));
  };

  let normal = normalize(cross(tangentAt(0), Math.abs(tangentAt(0)[2]) > 0.9 ? [1, 0, 0] : [0, 0, 1]));
  const rings: number[][] = [];
  const ringNormals: Vec3[] = [];
  const ringBinormals: Vec3[] = [];
  for (let i = 0; i < pts.length; i++) {
    const t = tangentAt(i);
    normal = normalize(sub(normal, vscale(t, dot(normal, t))));
    const binormal = normalize(cross(t, normal));
    ringNormals.push(normal);
    ringBinormals.push(binormal);
    const ring: number[] = [];
    for (let s = 0; s <= radial; s++) {
      const a = (s / radial) * TAU;
      const n = add(vscale(normal, Math.cos(a)), vscale(binormal, Math.sin(a)));
      ring.push(b.vertex(add(pts[i]!, vscale(n, radius)), n));
    }
    rings.push(ring);
  }

  const segments = closed ? pts.length : pts.length - 1;
  for (let i = 0; i < segments; i++) {
    const next = (i + 1) % pts.length;
    for (let s = 0; s < radial; s++) {
      b.quad(rings[i]![s]!, rings[i]![s + 1]!, rings[next]![s + 1]!, rings[next]![s]!);
    }
  }

  if (!closed) {
    const cap = (index: number, sign: number) => {
      const t = tangentAt(index);
      const n = ringNormals[index]!;
      const bn = ringBinormals[index]!;
      const center = b.vertex(pts[index]!, vscale(t, sign));
      const ring: number[] = [];
      for (let s = 0; s <= radial; s++) {
        const a = (s / radial) * TAU;
        const p = add(pts[index]!, vscale(add(vscale(n, Math.cos(a)), vscale(bn, Math.sin(a))), radius));
        ring.push(b.vertex(p, vscale(t, sign)));
      }
      for (let s = 0; s < radial; s++) {
        if (sign > 0) b.tri(center, ring[s]!, ring[s + 1]!);
        else b.tri(center, ring[s + 1]!, ring[s]!);
      }
    };
    cap(0, -1);
    cap(pts.length - 1, 1);
  }

  return b.build();
}

export function helix(radius: number, height: number, turns: number, wire: number, points = 96): Mesh {
  const path: Vec3[] = [];
  const count = Math.max(8, points);
  for (let i = 0; i <= count; i++) {
    const a = (i / count) * turns * TAU;
    path.push([radius * Math.cos(a), radius * Math.sin(a), -height / 2 + (i / count) * height]);
  }
  return tube(path, wire, { radialSegments: 8 });
}

// ── Gear ─────────────────────────────────────────────────────────────────────

export function gear(teeth = 18, radius = 20, h = 6, toothDepth = 4): Mesh {
  const count = Math.max(6, Math.min(64, Math.round(teeth)));
  const root = Math.max(1, radius - Math.max(0.5, toothDepth));
  const pitch = TAU / count;
  const outline: Array<[number, number]> = [];
  for (let i = 0; i < count; i++) {
    const a = i * pitch;
    const pts: Array<[number, number]> = [
      [root, a],
      [radius, a + pitch * 0.16],
      [radius, a + pitch * 0.44],
      [root, a + pitch * 0.6],
      [root, a + pitch],
    ];
    for (const [r, angle] of pts) {
      outline.push([r * Math.cos(angle), r * Math.sin(angle)]);
    }
  }
  return extrude(outline, h);
}

export { rad, TAU };
