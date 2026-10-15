// ── Schema metadata (introspected from the zod contract) ──────────────────────
//
// A compact, client-safe description of every block type's shape — required
// fields, kinds, enum values, array element shapes and (shallowly) object item
// fields — derived LIVE from `ResponseBlockSchema` so it cannot drift from the
// renderer. The repair engine (`repair.ts`) is DRIVEN by this metadata, which is
// why repair is generic rather than a growing list of special cases.
//
// Pure and framework-free: no React, no network. Derived once and cached.

import { ResponseBlockSchema } from './contract';

export type FieldKind = 'string' | 'number' | 'boolean' | 'enum' | 'array' | 'object' | 'unknown';

export interface FieldMeta {
  name: string;
  required: boolean;
  kind: FieldKind;
  /** Present for `kind: 'enum'`: the ONLY accepted values. */
  enumValues?: string[];
  /** Present for `kind: 'array'`: the element's shape. */
  element?: FieldMeta;
  /** Present for `kind: 'object'`: its fields (bounded depth). */
  fields?: FieldMeta[];
}

export interface BlockMeta {
  type: string;
  fields: FieldMeta[];
}

type AnySchema = {
  def?: Record<string, unknown>;
  shape?: Record<string, unknown>;
  isOptional?: () => boolean;
  options?: unknown[];
};

const asSchema = (schema: unknown): AnySchema => (schema ?? {}) as AnySchema;

// Wrapper schema types that hide the underlying type; unwrap to reach it.
const WRAPPER_TYPES = new Set(['optional', 'default', 'nullable', 'readonly', 'catch', 'prefault']);

function unwrap(schema: unknown): unknown {
  let current = schema;
  for (let i = 0; i < 6; i++) {
    const def = asSchema(current).def;
    if (!def || !WRAPPER_TYPES.has(String(def.type)) || def.innerType === undefined) break;
    current = def.innerType;
  }
  return current;
}

function isRequired(schema: unknown): boolean {
  const candidate = asSchema(schema);
  return !(typeof candidate.isOptional === 'function' && candidate.isOptional());
}

// Deep schemas are not needed: repair only reaches a couple of levels (arrays of
// objects, and their scalar/array fields). Bounded on purpose.
const MAX_DEPTH = 3;

function fieldMeta(name: string, schema: unknown, depth: number): FieldMeta {
  const required = isRequired(schema);
  const bare = unwrap(schema);
  const type = typeof asSchema(bare).def?.type === 'string' ? (asSchema(bare).def?.type as string) : 'unknown';

  if (type === 'enum') {
    const entries = asSchema(bare).def?.entries as Record<string, unknown> | undefined;
    return { name, required, kind: 'enum', enumValues: entries ? Object.keys(entries) : [] };
  }
  if (type === 'array') {
    return { name, required, kind: 'array', element: fieldMeta('', asSchema(bare).def?.element, depth + 1) };
  }
  if (type === 'object') {
    const shape = asSchema(bare).shape ?? {};
    const fields =
      depth >= MAX_DEPTH
        ? []
        : Object.entries(shape)
            .filter(([key]) => key !== 'type')
            .map(([key, value]) => fieldMeta(key, value, depth + 1));
    return { name, required, kind: 'object', fields };
  }
  if (type === 'string' || type === 'number' || type === 'boolean') {
    return { name, required, kind: type };
  }
  // Literal / union / lazy / record / etc.
  return { name, required, kind: 'unknown' };
}

let cache: Map<string, BlockMeta> | null = null;

/** The live field metadata for every registered block type (cached). */
export function responseBlockMeta(): Map<string, BlockMeta> {
  if (cache) return cache;
  const map = new Map<string, BlockMeta>();
  const union = ResponseBlockSchema as unknown as { options?: unknown[] };
  for (const option of union.options ?? []) {
    const shape = asSchema(option).shape ?? {};
    const typeDef = asSchema(shape.type).def;
    const values = typeDef?.values as unknown[] | undefined;
    const type = String(typeDef?.value ?? values?.[0] ?? '?');
    const fields = Object.entries(shape)
      .filter(([key]) => key !== 'type')
      .map(([key, value]) => fieldMeta(key, value, 0));
    map.set(type, { type, fields });
  }
  cache = map;
  return map;
}
