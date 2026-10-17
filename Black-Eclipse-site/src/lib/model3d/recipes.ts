// ── The mechanism kit ────────────────────────────────────────────────────────
//
// Reusable, PARAMETRIC assemblies made from the primitive meshes. The model
// composes scenes from these recipes instead of hand-guessing primitives — this
// is what turns "a pile of cylinders" into a recognisable machine.
//
// Recipes are pure data builders: same params in = same parts out. They carry no
// code, network access or randomness, and their output is bounded by the caller.
// Every recipe builds resting on z = 0 (legs/feet down) and is centred on x/y.

import type { Model3dKind, Model3dMaterial, Model3dTone } from './names';
import type { Vec3 } from './math';

export interface RecipePart {
  kind: Model3dKind;
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
  position?: Vec3;
  rotation?: Vec3;
  material?: Model3dMaterial;
  tone?: Model3dTone;
  lit?: boolean;
}

export type RecipeParams = Record<string, number>;
export type Recipe = (params: RecipeParams) => RecipePart[];

const p = (params: RecipeParams, key: string, fallback: number): number => {
  const value = params[key];
  return Number.isFinite(value) ? value! : fallback;
};

const bolt = (x: number, y: number, z: number, tone?: Model3dTone): RecipePart[] => [
  { kind: 'cylinder', radius: 1.1, h: 2, position: [x, y, z], material: 'metal', tone },
  { kind: 'cylinder', radius: 1.8, h: 1, position: [x, y, z + 1.4], material: 'metal', tone },
];

const motor: Recipe = (params) => {
  const r = p(params, 'radius', 12);
  const h = p(params, 'length', 34);
  const z = r + 2;
  return [
    { kind: 'box', w: h + 8, d: r * 2.2, h: 4, position: [0, 0, 2], material: 'paint' },
    { kind: 'cylinder', radius: r, h, rotation: [0, 90, 0], position: [0, 0, z], material: 'paint' },
    { kind: 'cylinder', radius: r + 1, h: 3, rotation: [0, 90, 0], position: [-h / 2 - 1.5, 0, z], material: 'metal' },
    { kind: 'cylinder', radius: r + 1, h: 3, rotation: [0, 90, 0], position: [h / 2 + 1.5, 0, z], material: 'metal' },
    { kind: 'cylinder', radius: r * 0.22, h: 16, rotation: [0, 90, 0], position: [h / 2 + 11, 0, z], material: 'metal' },
    { kind: 'cylinder', radius: r * 0.55, h: 2, rotation: [0, 90, 0], position: [h / 2 + 3.5, 0, z], material: 'metal' },
    ...[-h * 0.3, h * 0.3].flatMap((x) => bolt(x, r * 0.7, z + r * 0.9)),
  ];
};

const gearbox: Recipe = (params) => {
  const w = p(params, 'width', 46);
  const d = p(params, 'depth', 36);
  const h = p(params, 'height', 28);
  return [
    { kind: 'box', w: w + 12, d: d + 8, h: 6, position: [0, 0, 3], material: 'paint' },
    { kind: 'box', w, d, h, position: [0, 0, h / 2 + 6], material: 'paint' },
    { kind: 'box', w: w + 2, d: d + 2, h: 3, position: [0, 0, h + 7.5], material: 'metal' },
    { kind: 'gear', radius: p(params, 'gearRadius', 13), h: 5, teeth: 20, toothDepth: 2.4, rotation: [90, 0, 0], position: [-w / 2 - 1, 0, h / 2 + 6], material: 'metal' },
    { kind: 'cylinder', radius: 2.5, h: 20, rotation: [0, 90, 0], position: [-w / 2 - 8, 0, h / 2 + 6], material: 'metal' },
    { kind: 'cylinder', radius: 3.5, h: 20, rotation: [0, 90, 0], position: [w / 2 + 8, 0, h / 2 + 6], material: 'metal' },
    { kind: 'cylinder', radius: 5, h: 4, rotation: [0, 90, 0], position: [w / 2 + 1, 0, h / 2 + 6], material: 'metal' },
    ...[[-1, -1], [1, -1], [-1, 1], [1, 1]].flatMap(([sx, sy]) =>
      bolt(sx! * (w / 2 - 4), sy! * (d / 2 - 4), h + 9),
    ),
  ];
};

const pump: Recipe = (params) => {
  const r = p(params, 'radius', 16);
  return [
    { kind: 'box', w: r * 2.8, d: r * 1.8, h: 5, position: [0, 0, 2.5], material: 'paint' },
    { kind: 'cylinder', radius: r, h: 16, rotation: [0, 90, 0], position: [0, 0, r + 5], material: 'paint' },
    { kind: 'cylinder', radius: r * 0.42, h: 20, rotation: [0, 90, 0], position: [r * 0.5, 0, r + 5], material: 'metal' },
    { kind: 'cylinder', radius: r * 0.62, h: 3, rotation: [0, 90, 0], position: [r + 1.5, 0, r + 5], material: 'metal' },
    { kind: 'tube', radius: 4.5, path: [[-r * 0.6, 0, r + 5], [-r * 0.6, 0, r + 18], [-r * 0.6, r * 1.2, r + 22]], material: 'paint' },
    { kind: 'tube', radius: 5, path: [[r * 0.2, 0, r + 5], [r * 1.4, 0, r + 5], [r * 2.1, 0, r + 3]], material: 'metal' },
  ];
};

const valve: Recipe = (params) => {
  const r = p(params, 'radius', 9);
  return [
    { kind: 'cylinder', radius: r * 1.5, h: 2, position: [0, 0, 1], material: 'metal' },
    { kind: 'cylinder', radius: r, h: 14, position: [0, 0, 9], material: 'paint' },
    { kind: 'cylinder', radius: r * 1.45, h: 2, position: [0, 0, 17], material: 'metal' },
    { kind: 'cone', radius: r * 0.8, radiusTop: r * 0.45, h: 6, position: [0, 0, 21], material: 'metal' },
    { kind: 'cylinder', radius: 2, h: 12, position: [0, 0, 30], material: 'metal' },
    { kind: 'torus', radius: r * 1.1, tube: 1.3, position: [0, 0, 37], material: 'paint' },
    ...[0, 60, 120].map((a) => ({
      kind: 'box' as const,
      w: r * 2.2,
      d: 1.4,
      h: 1.4,
      rotation: [0, 0, a] as Vec3,
      position: [0, 0, 37] as Vec3,
      material: 'paint' as const,
    })),
    { kind: 'tube', radius: 2.6, path: [[-r * 1.8, 0, 9], [-r * 3.2, 0, 9]], material: 'metal' },
    { kind: 'tube', radius: 2.6, path: [[r * 1.8, 0, 9], [r * 3.2, 0, 9]], material: 'metal' },
  ];
};

const gauge: Recipe = (params) => {
  const r = p(params, 'radius', 9);
  return [
    { kind: 'cylinder', radius: 1.6, h: 10, rotation: [90, 0, 0], position: [0, 5, r + 2], material: 'metal' },
    { kind: 'cylinder', radius: r, h: 4, rotation: [90, 0, 0], position: [0, 0, r + 6], material: 'paint' },
    { kind: 'torus', radius: r, tube: 1.2, rotation: [90, 0, 0], position: [0, -2.2, r + 6], material: 'metal' },
    { kind: 'cylinder', radius: r * 0.86, h: 0.8, rotation: [90, 0, 0], position: [0, -2.9, r + 6], material: 'plastic' },
    { kind: 'box', w: 1.2, d: 0.8, h: r * 0.8, position: [0, -3.6, r + 6 + r * 0.32], rotation: [0, 0, 18], material: 'emissive', tone: 'warning' },
    { kind: 'sphere', radius: 1.1, position: [0, -3.7, r + 6], material: 'metal' },
  ];
};

const tank: Recipe = (params) => {
  const r = p(params, 'radius', 18);
  const h = p(params, 'height', 40);
  return [
    ...[[0, 0], [120, 0], [240, 0]].map(([a], i) => ({
      kind: 'box' as const,
      w: 3,
      d: 3,
      h: 8,
      position: [r * 0.72 * Math.cos((a! * Math.PI) / 180), r * 0.72 * Math.sin((a! * Math.PI) / 180), 4] as Vec3,
      material: 'metal' as const,
      tone: i === 2 ? 'info' as const : undefined,
    })),
    {
      kind: 'lathe',
      profile: [[8, r * 0.78], [10, r], [h * 0.82, r], [h * 0.92, r * 0.86], [h, r * 0.55]],
      position: [0, 0, 0],
      material: 'paint',
    },
    { kind: 'torus', radius: r * 1.01, tube: 0.8, position: [0, 0, 14], material: 'metal' },
    { kind: 'torus', radius: r * 1.01, tube: 0.8, position: [0, 0, h * 0.7], material: 'metal' },
    { kind: 'tube', radius: 2.4, path: [[r * 0.55, 0, h], [r * 0.55, 0, h + 10], [r * 1.1, 0, h + 14]], material: 'metal' },
  ];
};

const bearing: Recipe = (params) => {
  const r = p(params, 'radius', 12);
  const balls = Math.max(6, Math.min(14, Math.round(p(params, 'balls', 9))));
  return [
    { kind: 'torus', radius: r, tube: 2.6, material: 'metal' },
    { kind: 'torus', radius: r * 0.46, tube: 1.8, material: 'metal' },
    ...Array.from({ length: balls }, (_, i) => {
      const a = (i / balls) * Math.PI * 2;
      const rr = r * 0.73;
      return {
        kind: 'sphere' as const,
        radius: r * 0.19,
        position: [rr * Math.cos(a), rr * Math.sin(a), 0] as Vec3,
        material: 'metal' as const,
      };
    }),
    { kind: 'cylinder', radius: r * 0.3, h: 10, material: 'metal' },
  ];
};

const gear: Recipe = (params) => {
  const r = p(params, 'radius', 20);
  const teeth = Math.max(6, Math.round(p(params, 'teeth', 18)));
  return [
    { kind: 'gear', radius: r, h: p(params, 'thickness', 6), teeth, toothDepth: Math.max(1, r * 0.16), material: 'metal' },
    { kind: 'cylinder', radius: r * 0.3, h: p(params, 'hub', 12), material: 'metal' },
    { kind: 'box', w: 2, d: 5, h: 3, position: [r * 0.12, 0, 0], material: 'paint', tone: 'warning' },
  ];
};

const pulley: Recipe = (params) => {
  const r = p(params, 'radius', 14);
  return [
    { kind: 'lathe', profile: [[-6, r * 0.72], [-4, r], [0, r * 0.8], [4, r], [6, r * 0.72]], material: 'metal' },
    { kind: 'cylinder', radius: r * 0.28, h: 16, material: 'metal' },
    { kind: 'cylinder', radius: r * 0.34, h: 2, position: [0, 0, 7], material: 'paint', tone: 'info' },
  ];
};

const beltDrive: Recipe = (params) => {
  const r = p(params, 'radius', 12);
  const span = p(params, 'span', 34);
  const z = p(params, 'height', 18);
  const belt: Vec3[] = [];
  const steps = 12;
  for (let i = 0; i <= steps; i++) {
    const a = -Math.PI / 2 + (i / steps) * Math.PI;
    belt.push([span + r * Math.cos(a), 0, z + r * Math.sin(a)]);
  }
  for (let i = 0; i <= steps; i++) {
    const a = Math.PI / 2 + (i / steps) * Math.PI;
    belt.push([-span + r * Math.cos(a), 0, z + r * Math.sin(a)]);
  }
  return [
    { kind: 'box', w: span * 2 + r * 2, d: 18, h: 4, position: [0, 0, 2], material: 'paint' },
    { kind: 'lathe', profile: [[-6, r * 0.72], [-4, r], [0, r * 0.8], [4, r], [6, r * 0.72]], rotation: [90, 0, 0], position: [-span, 0, z], material: 'metal' },
    { kind: 'lathe', profile: [[-6, r * 0.72], [-4, r], [0, r * 0.8], [4, r], [6, r * 0.72]], rotation: [90, 0, 0], position: [span, 0, z], material: 'metal' },
    { kind: 'cylinder', radius: 2, h: 26, rotation: [0, 90, 0], position: [-span, 0, z], material: 'metal' },
    { kind: 'cylinder', radius: 2, h: 26, rotation: [0, 90, 0], position: [span, 0, z], material: 'metal' },
    { kind: 'tube', radius: 1.6, path: belt, closed: true, material: 'rubber' },
    { kind: 'box', w: 4, d: 6, h: z, position: [-span, 0, z / 2], material: 'paint' },
    { kind: 'box', w: 4, d: 6, h: z, position: [span, 0, z / 2], material: 'paint' },
  ];
};

const frame: Recipe = (params) => {
  const w = p(params, 'width', 70);
  const d = p(params, 'depth', 34);
  return [
    ...[-1, 1].flatMap((s) => [
      { kind: 'box' as const, w, d: 5, h: 5, position: [0, (s * d) / 2, 8] as Vec3, material: 'metal' as const },
      { kind: 'box' as const, w: 5, d: d - 4, h: 5, position: [(s * w) / 2, 0, 8] as Vec3, material: 'metal' as const },
    ]),
    ...[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sy]) => ({
      kind: 'box' as const, w: 6, d: 6, h: 8, position: [sx! * (w / 2 - 5), sy! * (d / 2 - 5), 4] as Vec3, material: 'paint' as const,
    })),
    { kind: 'box', w: w - 10, d: d - 10, h: 1.5, position: [0, 0, 9], material: 'metal', tone: 'info' },
  ];
};

const bracket: Recipe = (params) => {
  const h = p(params, 'height', 22);
  return [
    { kind: 'box', w: 5, d: 22, h, position: [0, 0, h / 2], material: 'metal' },
    { kind: 'box', w: 20, d: 22, h: 5, position: [10, 0, 2.5], material: 'metal' },
    { kind: 'box', w: 14, d: 4, h: 4, position: [11, 0, h - 4], rotation: [0, 30, 0], material: 'metal' },
    ...[[-1, -1], [1, -1], [-1, 1], [1, 1]].flatMap(([, sy]) =>
      bolt(0, sy! * 8, h - 3, 'success'),
    ),
  ];
};

const fan: Recipe = (params) => {
  const r = p(params, 'radius', 14);
  return [
    { kind: 'cylinder', radius: 3, h: 9, position: [0, 0, 4.5], material: 'metal' },
    { kind: 'cylinder', radius: r * 0.32, h: 6, position: [0, 0, 11], material: 'paint' },
    { kind: 'torus', radius: r, tube: 1.6, position: [0, 0, 11], material: 'metal' },
    ...Array.from({ length: 6 }, (_, i) => {
      const a = (i / 6) * Math.PI * 2;
      return {
        kind: 'box' as const,
        w: r * 0.8,
        d: 4,
        h: 1.2,
        position: [Math.cos(a) * r * 0.42, Math.sin(a) * r * 0.42, 11] as Vec3,
        rotation: [0, 0, (a * 180) / Math.PI] as Vec3,
        material: 'metal' as const,
        tone: i === 0 ? ('info' as const) : undefined,
      };
    }),
  ];
};

const heatExchanger: Recipe = (params) => {
  const r = p(params, 'radius', 11);
  const h = p(params, 'length', 46);
  return [
    ...[-h * 0.28, h * 0.28].map((x) => ({
      kind: 'box' as const, w: 8, d: r * 2.1, h: 8, position: [x, 0, 4] as Vec3, material: 'paint' as const,
    })),
    { kind: 'cylinder', radius: r, h, rotation: [0, 90, 0], position: [0, 0, r + 8], material: 'paint' },
    { kind: 'cylinder', radius: r + 1.2, h: 3, rotation: [0, 90, 0], position: [-h / 2, 0, r + 8], material: 'metal' },
    { kind: 'cylinder', radius: r + 1.2, h: 3, rotation: [0, 90, 0], position: [h / 2, 0, r + 8], material: 'metal' },
    ...[-6, -3, 0, 3, 6].flatMap((y) => [
      { kind: 'cylinder' as const, radius: 1.2, h: h + 6, rotation: [0, 90, 0] as Vec3, position: [0, y, r + 8 + 5] as Vec3, material: 'metal' as const },
      { kind: 'cylinder' as const, radius: 1.2, h: h + 6, rotation: [0, 90, 0] as Vec3, position: [0, y, r + 8 - 5] as Vec3, material: 'metal' as const },
    ]),
    { kind: 'tube', radius: 3, path: [[-h * 0.25, 0, r + 8], [-h * 0.25, 0, r + 20], [-h * 0.25, 8, r + 24]], material: 'metal' },
    { kind: 'tube', radius: 3, path: [[h * 0.25, 0, r + 8], [h * 0.25, 0, r + 20], [h * 0.25, -8, r + 24]], material: 'metal' },
  ];
};

const pcb: Recipe = (params) => {
  const w = p(params, 'width', 44);
  const d = p(params, 'depth', 30);
  return [
    { kind: 'box', w, d, h: 1.6, position: [0, 0, 6], material: 'plastic', tone: 'success' },
    ...[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sy]) => ({
      kind: 'cylinder' as const, radius: 1.6, h: 4, position: [sx! * (w / 2 - 4), sy! * (d / 2 - 4), 2] as Vec3, material: 'metal' as const,
    })),
    { kind: 'box', w: 16, d: 12, h: 2.4, position: [-8, 2, 8], material: 'metal', tone: 'info' },
    { kind: 'box', w: 9, d: 9, h: 3, position: [11, -3, 8.2], material: 'metal' },
    { kind: 'box', w: 12, d: 5, h: 4, position: [8, 9, 8.6], material: 'plastic' },
    { kind: 'cylinder', radius: 3.2, h: 5, position: [-16, -10, 9], material: 'metal', tone: 'warning' },
    { kind: 'box', w: w - 8, d: 1.4, h: 0.4, position: [0, -d / 2 + 3, 7], material: 'emissive', tone: 'success' },
  ];
};

const lever: Recipe = (params) => {
  const arm = p(params, 'arm', 40);
  return [
    { kind: 'box', w: 18, d: 14, h: 4, position: [0, 0, 2], material: 'paint' },
    { kind: 'cylinder', radius: 3.4, h: 7, position: [0, 0, 6], material: 'metal' },
    { kind: 'box', w: arm, d: 3, h: 2.4, position: [arm * 0.38, 0, 8], rotation: [0, -14, 0], material: 'metal' },
    { kind: 'sphere', radius: 3.2, position: [arm * 0.78, 0, 11.5], material: 'rubber' },
    { kind: 'box', w: 3, d: 3, h: 10, position: [-arm * 0.28, 0, 8], material: 'metal', tone: 'danger' },
  ];
};

const spring: Recipe = (params) => {
  const r = p(params, 'radius', 8);
  const h = p(params, 'height', 24);
  return [
    { kind: 'cylinder', radius: r * 1.3, h: 2, position: [0, 0, 1], material: 'metal' },
    { kind: 'cylinder', radius: 1.6, h: h + 4, position: [0, 0, h / 2 + 2], material: 'metal' },
    { kind: 'tube', radius: 1.5, path: Array.from({ length: 97 }, (_, i) => {
      const t = i / 96;
      const a = t * 7 * Math.PI * 2;
      return [r * Math.cos(a), r * Math.sin(a), 3 + t * h] as Vec3;
    }), material: 'metal', tone: 'info' },
    { kind: 'cylinder', radius: r * 1.3, h: 2, position: [0, 0, h + 3], material: 'metal' },
  ];
};

export const RECIPES: Record<string, Recipe> = {
  motor,
  gearbox,
  pump,
  valve,
  gauge,
  tank,
  bearing,
  gear,
  pulley,
  'belt-drive': beltDrive,
  frame,
  bracket,
  fan,
  'heat-exchanger': heatExchanger,
  pcb,
  lever,
  spring,
};
