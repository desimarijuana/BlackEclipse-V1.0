// ── Shared model3d vocabulary ────────────────────────────────────────────────
//
// Kept in its own tiny module so the zod schema (`response/blocks/model3d.ts`)
// and the geometry/recipe runtime agree on the SAME names without importing
// geometry into the contract. A drift here is caught by `model3d-schema.test.ts`.

export const MODEL3D_KINDS = [
  'box',
  'cylinder',
  'cone',
  'sphere',
  'torus',
  'lathe',
  'extrude',
  'tube',
  'gear',
] as const;

export const MODEL3D_RECIPES = [
  'motor',
  'gearbox',
  'pump',
  'valve',
  'gauge',
  'tank',
  'bearing',
  'gear',
  'pulley',
  'belt-drive',
  'frame',
  'bracket',
  'fan',
  'heat-exchanger',
  'pcb',
  'lever',
  'spring',
] as const;

export const MODEL3D_MATERIALS = [
  'metal',
  'paint',
  'rubber',
  'glass',
  'plastic',
  'emissive',
] as const;

export const MODEL3D_TONES = ['neutral', 'info', 'success', 'warning', 'danger'] as const;

export type Model3dKind = (typeof MODEL3D_KINDS)[number];
export type Model3dRecipe = (typeof MODEL3D_RECIPES)[number];
export type Model3dMaterial = (typeof MODEL3D_MATERIALS)[number];
export type Model3dTone = (typeof MODEL3D_TONES)[number];
