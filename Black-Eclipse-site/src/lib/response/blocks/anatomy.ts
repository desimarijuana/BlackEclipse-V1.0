// ── `anatomy` block schema ────────────────────────────────────────────────────
//
// Extracted from `response/contract.ts` (the file is over its size ratchet; this
// is the named standing split — block schemas move into `response/blocks/`). It
// is deliberately SELF-CONTAINED: it does not import from `../contract`, because
// contract.ts imports THIS module to build its discriminated union — a value
// import back would create a circular-initialization crash (the schema is built
// at module top level, before contract.ts has assigned its constants).
//
// An interactive isometric mechanism figure: a bounded, declarative SCENE the
// model authors (parts, wires, legend, deterministic stages). The geometry is
// compiled purely by `lib/anatomy/scene.ts`; the model never supplies SVG or code.

import { z } from 'zod';

// Mirrors the contract's shared primitives (kept local to avoid the import cycle).
const shortString = z.string().max(500);
const idString = z.string().min(1).max(120);

// Bounds mirror RESPONSE_LIMITS (which cannot be imported here — see the header).
const MAX_PARTS = 64;
const MAX_WIRES = 128;
const MAX_LEGEND = 12;
const MAX_STAGES = 12;

// Tone uses the SAME status vocabulary as every other response block
// (neutral/info/success/warning/danger) — this is what the model is already
// taught and naturally emits, and `normalize.ts` maps synonyms onto it. A part
// tone colours its outline; a wire tone colours the line.
const anatomyTone = z.enum(['neutral', 'info', 'success', 'warning', 'danger']);

const anatomyPartSchema = z.object({
  id: idString,
  /** `slab` rounded box · `prism` extruded plan polygon · `cylinder`/`disc`
   *  round columns · `knob` knurled control · `lathe`/`cone`/`sphere` TURNED
   *  solids from the kit's lathe (bells, flanges, domes, balls). */
  kind: z.enum(['slab', 'prism', 'cylinder', 'disc', 'knob', 'lathe', 'cone', 'sphere']).default('slab'),
  x: z.number().finite().default(0),
  y: z.number().finite().default(0),
  z: z.number().finite().default(0),
  w: z.number().finite().positive().optional(),
  d: z.number().finite().positive().optional(),
  radius: z.number().finite().positive().optional(),
  /** A `cone`'s top radius (default 0 = a point); a `lathe` ignores it. */
  radiusTop: z.number().finite().min(0).optional(),
  /** A `prism`'s floor plan polygon (x, y world points). */
  points: z.array(z.tuple([z.number().finite(), z.number().finite()])).min(3).max(24).optional(),
  /** A `lathe`'s turning profile: `[axial, radius]` pairs (axial runs up `z`). */
  profile: z.array(z.tuple([z.number().finite(), z.number().finite()])).min(2).max(24).optional(),
  /** A `lathe` profile with smooth knots: shade it as one curved body. */
  smooth: z.boolean().optional(),
  height: z.number().finite().positive().default(16),
  corner: z.number().finite().min(0).optional(),
  tone: anatomyTone.default('neutral'),
  lit: z.boolean().optional(),
  halo: z.boolean().optional(),
  label: shortString.optional(),
  // ── Craft decorations (each belongs to the part) ──────────────────────────
  /** A shallow inset rule on the top face. */
  groove: z.boolean().optional(),
  /** Corner screws on a slab/prism top face. */
  screws: z.boolean().optional(),
  /** Knurl lines around a round part (a grip). */
  knurl: z.boolean().optional(),
  knurlCount: z.number().int().min(6).max(60).optional(),
  /** Ruler ticks along the top edge: a count, or `{ count, every }`. */
  ticks: z.union([
    z.number().int().min(2).max(40),
    z.object({ count: z.number().int().min(2).max(40), every: z.number().int().min(1).max(10).optional() }),
  ]).optional(),
});

const anatomyWireSchema = z.object({
  from: idString,
  to: idString,
  /** Optional world-space waypoints (x, y, z) the wire routes through. */
  via: z.array(z.array(z.number().finite()).length(3)).max(8).optional(),
  tone: anatomyTone.default('neutral'),
  dotted: z.boolean().optional(),
  dashed: z.boolean().optional(),
  flow: z.boolean().optional(),
  label: shortString.optional(),
});

const anatomyLegendSchema = z.object({
  label: shortString,
  /** A free-form hint ("tall cylinder", "dashed wire"); known marks get a
   *  shaped swatch, anything else a neutral one. Never fails the block. */
  mark: z.string().max(40).optional(),
});

const anatomyStageSchema = z.object({
  label: shortString,
  note: shortString.optional(),
  /** A readout shown while this stage is active — the figure's only source of
   *  live text, so a number can never be invented by the animation. */
  readout: shortString.optional(),
  /** Parts highlighted while this stage is active. A boolean is accepted (true
   *  = every part, false = none) so a natural producer shape is not rejected. */
  lit: z.union([z.boolean(), z.array(idString).max(MAX_PARTS)]).default([]),
});

export const anatomyBlock = z.object({
  type: z.literal('anatomy'),
  id: idString.optional(),
  title: shortString.optional(),
  fig: shortString.optional(),
  hint: shortString.optional(),
  readout: shortString.optional(),
  caption: shortString.optional(),
  description: shortString.optional(),
  width: z.number().int().min(120).max(2000).default(760),
  height: z.number().int().min(120).max(1200).default(480),
  azimuth: z.number().finite().min(-180).max(180).default(45),
  elevation: z.number().finite().min(5).max(85).default(30),
  parts: z.array(anatomyPartSchema).max(MAX_PARTS).default([]),
  wires: z.array(anatomyWireSchema).max(MAX_WIRES).default([]),
  legend: z.array(anatomyLegendSchema).max(MAX_LEGEND).default([]),
  stages: z.array(anatomyStageSchema).max(MAX_STAGES).default([]),
  /** Opt-in autoplay of the stages (when there is more than one). Quiet by
   *  default; never plays under `prefers-reduced-motion`. */
  animate: z.boolean().optional(),
});

export type AnatomyBlock = z.infer<typeof anatomyBlock>;
