// ── `model3d` block schema ───────────────────────────────────────────────────
//
// A real 3D scene: the model authors a graph of parametric parts and reusable
// mechanism recipes, never meshes, shaders or code. `lib/model3d/compile.ts`
// resolves the graph into world-space triangles; the renderer only uploads them.
//
// Why a separate block from `anatomy`: the legacy anatomy block compiles a
// painter-order isometric SVG and cannot rotate, depth-test or compose. This
// block keeps the same trust model (declarative data, bounded, total) but its
// output is a true 3D model (orbitable in chat, exportable as glTF/GLB).
//
// Self-contained like every `response/blocks/*` schema (no import back into
// contract.ts — see blocks/anatomy.ts for the circular-init reason).

import { z } from 'zod';
import {
  MODEL3D_KINDS,
  MODEL3D_MATERIALS,
  MODEL3D_RECIPES,
  MODEL3D_TONES,
} from '@/lib/model3d/names';

const shortString = z.string().max(500);
const idString = z.string().min(1).max(120);
const number = z.number().finite();

const MAX_PARTS = 96;
const MAX_WIRES = 128;
const MAX_LEGEND = 12;
const MAX_STAGES = 12;

const vec3 = z.tuple([number, number, number]);

const model3dPartSchema = z.object({
  id: idString,
  /** Parent node id (assemblies). The parent's transform composes onto this one. */
  parent: idString.optional(),
  /** Primitive geometry, ignored when `recipe` is set. */
  kind: z.enum(MODEL3D_KINDS).default('box'),
  /** A reusable mechanism assembly (`motor`, `gearbox`, `pump`, …). */
  recipe: z.enum(MODEL3D_RECIPES).optional(),

  // ── Primitive dimensions (world units; the part is centred on its origin) ──
  w: z.number().finite().positive().optional(),
  d: z.number().finite().positive().optional(),
  h: z.number().finite().positive().optional(),
  radius: z.number().finite().positive().optional(),
  radiusTop: z.number().finite().min(0).optional(),
  tube: z.number().finite().positive().optional(),
  /** An `extrude` footprint polygon (x, y). */
  points: z.array(z.tuple([number, number])).min(3).max(64).optional(),
  /** A `lathe` profile: `[axial(z), radius]` pairs. */
  profile: z.array(z.tuple([number, number])).min(2).max(48).optional(),
  /** A `tube` centreline (x, y, z). */
  path: z.array(vec3).min(2).max(64).optional(),
  closed: z.boolean().optional(),
  /** A `gear`'s tooth count and tooth depth. */
  teeth: z.number().int().min(3).max(64).optional(),
  toothDepth: z.number().finite().positive().optional(),

  // ── Transform. Rotation is degrees, applied X then Y then Z (extrinsic). ──
  position: vec3.default([0, 0, 0]),
  rotation: vec3.default([0, 0, 0]),
  scale: vec3.optional(),

  // ── Look ──────────────────────────────────────────────────────────────────
  material: z.enum(MODEL3D_MATERIALS).default('paint'),
  tone: z.enum(MODEL3D_TONES).default('neutral'),
  opacity: z.number().finite().min(0).max(1).default(1),
  lit: z.boolean().optional(),
  label: shortString.optional(),

  // ── Recipe parameters (numbers only; unknown keys are ignored) ────────────
  params: z.record(z.string(), z.number().finite()).optional(),
});

const model3dWireSchema = z.object({
  from: idString,
  to: idString,
  tone: z.enum(MODEL3D_TONES).default('neutral'),
  dashed: z.boolean().optional(),
  dotted: z.boolean().optional(),
  label: shortString.optional(),
});

const model3dLegendSchema = z.object({
  label: shortString,
  mark: z.string().max(40).optional(),
});

const model3dStageSchema = z.object({
  label: shortString,
  note: shortString.optional(),
  readout: shortString.optional(),
  lit: z.union([z.boolean(), z.array(idString).max(MAX_PARTS)]).default([]),
});

const model3dCameraSchema = z.object({
  /** Orbit angle in degrees (0 = looking along -Y). */
  azimuth: z.number().finite().min(-360).max(360).default(45),
  /** Orbit elevation in degrees (0 = level, 90 = top-down). */
  elevation: z.number().finite().min(-5).max(89).default(28),
  /** Camera distance in world units; 0/omitted = fit to the scene. */
  distance: z.number().finite().positive().optional(),
  /** Orbit target; omitted = scene centre. */
  target: vec3.optional(),
});

export const model3dBlock = z.object({
  type: z.literal('model3d'),
  id: idString.optional(),
  title: shortString.optional(),
  fig: shortString.optional(),
  hint: shortString.optional(),
  readout: shortString.optional(),
  caption: shortString.optional(),
  description: shortString.optional(),
  width: z.number().int().min(200).max(2000).default(760),
  height: z.number().int().min(200).max(1200).default(520),
  camera: model3dCameraSchema.default({ azimuth: 45, elevation: 28 }),
  /** Drop the whole scene onto z = 0 when it floats above the ground. */
  ground: z.boolean().default(true),
  parts: z.array(model3dPartSchema).max(MAX_PARTS).default([]),
  wires: z.array(model3dWireSchema).max(MAX_WIRES).default([]),
  legend: z.array(model3dLegendSchema).max(MAX_LEGEND).default([]),
  stages: z.array(model3dStageSchema).max(MAX_STAGES).default([]),
  animate: z.boolean().optional(),
});

export type Model3dBlock = z.infer<typeof model3dBlock>;
export type Model3dPart = z.infer<typeof model3dPartSchema>;
export type Model3dStage = z.infer<typeof model3dStageSchema>;
