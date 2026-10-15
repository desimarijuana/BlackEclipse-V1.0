// ── Schema-directed block repair ──────────────────────────────────────────────
//
// When normalization leaves a block invalid, this pass makes ONE best-effort,
// DETERMINISTIC repair attempt driven by the introspected schema metadata
// (`schema-meta.ts`) — not by an ever-growing list of special cases. It covers
// the generic drift classes:
//
//   • a REQUIRED field is missing but the block carries a same-kind, non-schema
//     sibling (`name`/`label`/`title`/`datasets`/`points`/…)              → adopt it;
//   • an ENUM value is off (`bars`, `vertical`, `in-progress`)            → alias or nearest value;
//   • an ARRAY field arrived as a single value                            → wrap it;
//   • an OBJECT field arrived as a one-element array, or vice versa       → unwrap/wrap;
//   • a NUMBER/BOOLEAN/STRING arrived as a coercible scalar (`"12"`, `"yes"`) → coerce;
//   • unrecognized / unrepairable values                                  → dropped.
//
// The result is re-validated by the caller; if it still fails, the block is
// degraded (the Phase 1 backstop). Pure and total: never throws, never invents.

import type { FieldMeta } from './schema-meta';

const DROP = Symbol('repair-drop');
type Repaired = unknown | typeof DROP;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

// Donor names to prefer when rescuing a missing required field from a same-kind
// sibling, most-canonical first. Ties fall back to document order.
const DONOR_PREFERENCE = [
  'name', 'label', 'title', 'text', 'content', 'body', 'value',
  'data', 'values', 'points', 'datasets', 'series', 'sources',
  'items', 'steps', 'stages', 'rows', 'columns',
];

// Small, generic enum aliases that a nearest-value match cannot recover.
const ENUM_ALIASES: Record<string, string> = {
  'top-bottom': 'TB', top_to_bottom: 'TB', 'top-down': 'TB', vertical: 'TB', tb: 'TB',
  'left-right': 'LR', left_to_right: 'LR', 'left-to-right': 'LR', horizontal: 'LR', lr: 'LR',
  'in-progress': 'active', in_progress: 'active', running: 'active', started: 'active',
  complete: 'done', completed: 'done', finished: 'done', success: 'done',
  failed: 'error', failure: 'error', errored: 'error',
  queued: 'pending', todo: 'pending', 'not-started': 'pending',
  'flow-chart': 'flowchart', 'state-map': 'state', 'dependency-graph': 'dependency',
};

function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const curr = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
    }
    prev = curr;
  }
  return prev[b.length];
}

function nearestEnum(value: string, values: string[]): string | undefined {
  let best: string | undefined;
  let bestDistance = Infinity;
  for (const candidate of values) {
    const distance = levenshtein(value, candidate);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = candidate;
    }
  }
  if (best === undefined) return undefined;
  const tolerance = Math.max(1, Math.floor(Math.max(value.length, best.length) / 3));
  return bestDistance <= tolerance ? best : undefined;
}

/** True when `value` plausibly fills a field of the given kind (for donor search). */
function kindMatches(value: unknown, field: FieldMeta): boolean {
  switch (field.kind) {
    case 'array':
      return Array.isArray(value);
    case 'object':
      return isRecord(value);
    case 'enum':
    case 'string':
      return typeof value === 'string';
    case 'number':
      return typeof value === 'number' || (typeof value === 'string' && Number.isFinite(Number(value)));
    case 'boolean':
      return typeof value === 'boolean';
    default:
      return true;
  }
}

function coerceScalar(value: unknown, kind: 'string' | 'number' | 'boolean'): Repaired {
  if (kind === 'string') {
    if (typeof value === 'string') return value;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    return DROP;
  }
  if (kind === 'number') {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string') {
      const parsed = Number(value.replace(/[,%\s]/g, ''));
      if (Number.isFinite(parsed)) return parsed;
    }
    if (typeof value === 'boolean') return value ? 1 : 0;
    return DROP;
  }
  // boolean
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const lowered = value.trim().toLowerCase();
    if (['true', 'yes', 'y', '1'].includes(lowered)) return true;
    if (['false', 'no', 'n', '0'].includes(lowered)) return false;
  }
  return DROP;
}

function repairValue(value: unknown, field: FieldMeta): Repaired {
  switch (field.kind) {
    case 'enum': {
      const values = field.enumValues ?? [];
      const normalized = (typeof value === 'string' ? value : String(value)).trim().toLowerCase();
      if (values.includes(normalized)) return normalized;
      const aliased = ENUM_ALIASES[normalized];
      if (aliased && values.includes(aliased)) return aliased;
      return nearestEnum(normalized, values) ?? DROP;
    }
    case 'array': {
      const element = field.element;
      if (Array.isArray(value)) {
        const out: unknown[] = [];
        for (const item of value) {
          const repaired = element ? repairValue(item, element) : item;
          if (repaired !== DROP) out.push(repaired);
        }
        return out;
      }
      // A single value where an array is expected → wrap it.
      const repaired = element ? repairValue(value, element) : value;
      return repaired !== DROP ? [repaired] : DROP;
    }
    case 'object': {
      if (isRecord(value)) return repairObject(value, field.fields ?? []);
      if (Array.isArray(value) && isRecord(value[0])) return repairObject(value[0], field.fields ?? []);
      return DROP;
    }
    case 'string':
    case 'number':
    case 'boolean':
      return coerceScalar(value, field.kind);
    default:
      return value;
  }
}

/** Adopt a same-kind, non-schema sibling for a missing required field. */
function findDonor(object: Record<string, unknown>, field: FieldMeta, schemaNames: Set<string>): string | undefined {
  const candidates = Object.keys(object).filter(
    (key) => !schemaNames.has(key) && object[key] !== undefined && kindMatches(object[key], field),
  );
  if (candidates.length === 0) return undefined;
  for (const preferred of DONOR_PREFERENCE) if (candidates.includes(preferred)) return preferred;
  return candidates[0];
}

function repairObject(object: Record<string, unknown>, fields: FieldMeta[]): Record<string, unknown> {
  const out: Record<string, unknown> = { ...object };
  const schemaNames = new Set(fields.map((field) => field.name));

  // 1. Rescue missing required fields from a same-kind sibling.
  for (const field of fields) {
    if (!field.required || out[field.name] !== undefined) continue;
    const donor = findDonor(out, field, schemaNames);
    if (donor !== undefined) out[field.name] = out[donor];
  }

  // 2. Repair every present field in place.
  for (const field of fields) {
    if (out[field.name] === undefined) continue;
    const repaired = repairValue(out[field.name], field);
    if (repaired === DROP) delete out[field.name];
    else out[field.name] = repaired;
  }

  return out;
}

/**
 * Apply ONE deterministic repair attempt to a block's (already-normalized) raw
 * value, using its schema metadata. Returns the input unchanged when the block
 * type is unknown or no schema applies. The caller re-validates the result.
 */
export function repairUnknownBlock(raw: unknown, meta: FieldMeta[] | undefined): unknown {
  if (!isRecord(raw) || !meta) return raw;
  return repairObject(raw, meta);
}
