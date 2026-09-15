// ── Custom dataset mapping ──────────────────────────────────────────────────
// Turns an arbitrary JSON API response into flat, typed records.
//
// Path syntax (one consistent convention, used for both `recordPath` and field
// `sourcePath`):
//   - `$`            the root value itself
//   - `a.b.c`        nested object access
//   - `results[*]`   every element of the array at `results`
//
// `recordPath` selects the array (or single object) whose elements become
// `CustomDatasetRecord` rows. Field `sourcePath`s are resolved RELATIVE to each
// extracted record.

export type FieldType = "string" | "number" | "boolean" | "datetime" | "json";

export const FIELD_TYPES: FieldType[] = ["string", "number", "boolean", "datetime", "json"];

export interface DatasetField {
  name: string;
  type: FieldType;
  sourcePath: string;
  required?: boolean;
  /** Part of the dedup identity (see `computeRecordKey`). */
  identity?: boolean;
  description?: string;
  unit?: string;
}

export interface DatasetSchema {
  dataset: string;
  description?: string;
  /** e.g. `results[*]` for arrays, `$` for a single root object. */
  recordPath: string;
  fields: DatasetField[];
  timestampField?: string;
}

export interface MappedRecord {
  recordKey: string;
  values: Record<string, unknown>;
  /** The untouched source object, for auditing/inspection. */
  raw: unknown;
}

export class MappingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MappingError";
  }
}

/** Split a path into segments. `[*]` becomes the sentinel `"*"`. */
export function parsePath(path: string): string[] {
  if (path === "$" || path.trim() === "") return [];
  return path
    .split(".")
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .flatMap((segment) => {
      if (segment.endsWith("[*]")) {
        const head = segment.slice(0, -3);
        return head ? [head, "*"] : ["*"];
      }
      return [segment];
    });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Read a value at `path`. Returns `{ found, value }` so callers can distinguish
 * "missing" from "explicitly null".
 */
export function getPath(root: unknown, path: string): { found: boolean; value: unknown } {
  const segments = parsePath(path);
  let current: unknown = root;
  for (const segment of segments) {
    if (segment === "*") {
      if (!Array.isArray(current)) return { found: false, value: undefined };
      continue; // handled by the caller via extractRecords
    }
    if (!isRecord(current)) return { found: false, value: undefined };
    if (!(segment in current)) return { found: false, value: undefined };
    current = current[segment];
  }
  return { found: true, value: current };
}

/**
 * Extract the list of records a response describes.
 * - `results[*]` → every element of `results`
 * - `$`          → the root, wrapped in a one-element array
 */
export function extractRecords(root: unknown, recordPath: string): unknown[] {
  if (recordPath === "$" || recordPath.trim() === "") {
    return root === undefined ? [] : [root];
  }
  const segments = parsePath(recordPath);
  const wantsEvery = segments[segments.length - 1] === "*";
  if (!wantsEvery) {
    const { found, value } = getPath(root, recordPath);
    if (!found || value === undefined) return [];
    return Array.isArray(value) ? value : [value];
  }
  const containerPath = segments.slice(0, -1).join(".");
  const { found, value } = getPath(root, containerPath);
  if (!found || value === undefined) return [];
  if (Array.isArray(value)) return value;
  return [value];
}

/** Coerce one raw value to the declared field type. Returns `undefined` if invalid. */
export function coerce(value: unknown, type: FieldType): unknown {
  if (value === null || value === undefined) return undefined;
  switch (type) {
    case "string":
      if (typeof value === "object") return JSON.stringify(value);
      return String(value);
    case "number": {
      if (typeof value === "number") return Number.isFinite(value) ? value : undefined;
      const n = Number(String(value).replace(/,/g, ""));
      return Number.isFinite(n) ? n : undefined;
    }
    case "boolean": {
      if (typeof value === "boolean") return value;
      const s = String(value).toLowerCase();
      if (["true", "1", "yes", "y"].includes(s)) return true;
      if (["false", "0", "no", "n"].includes(s)) return false;
      return undefined;
    }
    case "datetime": {
      const d = value instanceof Date ? value : new Date(String(value));
      if (Number.isNaN(d.getTime())) return undefined;
      return d.toISOString();
    }
    case "json":
      return typeof value === "string" ? value : JSON.stringify(value);
    default:
      return undefined;
  }
}

/**
 * Deterministic identity for a record. Identity fields are the mapped fields
 * flagged `identity: true` (falling back to the timestamp/`symbol` fields, then
 * to the whole record). Re-importing the same response therefore produces the
 * same key and upserts instead of duplicating.
 */
export function computeRecordKey(values: Record<string, unknown>, fields: DatasetField[]): string | null {
  let identity = fields.filter((f) => f.identity).map((f) => f.name);
  if (identity.length === 0) {
    identity = fields.filter((f) => f.name === "symbol" || f.name === "timestamp").map((f) => f.name);
  }
  if (identity.length === 0) return null;
  const parts: string[] = [];
  for (const name of identity) {
    const value = values[name];
    if (value === undefined || value === null || value === "") return null;
    parts.push(String(value));
  }
  return parts.join("|");
}

export interface MapOutcome {
  records: MappedRecord[];
  /** Records the response contained (before mapping/dedup). */
  extracted: number;
  /** Dropped because a required field was missing or uncoercible. */
  rejectedRequired: number;
  /** Dropped because the record identity could not be computed. */
  rejectedIdentity: number;
  /** Collapsed onto an earlier record with the same key (last-write-wins). */
  deduped: number;
}

/**
 * Map a full response into records, reporting what was dropped.
 * Records whose identity cannot be computed are rejected (they cannot be
 * deduped safely); within a batch, later records with the same key overwrite
 * earlier ones (last-write-wins).
 */
export function mapResponseDetailed(root: unknown, schema: DatasetSchema): MapOutcome {
  const rawRecords = extractRecords(root, schema.recordPath);
  const byKey = new Map<string, MappedRecord>();
  let rejectedRequired = 0;
  let rejectedIdentity = 0;
  let deduped = 0;

  for (const raw of rawRecords) {
    const values: Record<string, unknown> = {};
    let missingRequired = false;

    for (const field of schema.fields) {
      const { found, value } = getPath(raw, field.sourcePath);
      const coerced = found ? coerce(value, field.type) : undefined;
      if (coerced === undefined) {
        if (field.required) {
          missingRequired = true;
          break;
        }
        continue;
      }
      values[field.name] = coerced;
    }
    if (missingRequired) {
      rejectedRequired++;
      continue;
    }

    const recordKey = computeRecordKey(values, schema.fields);
    if (!recordKey) {
      rejectedIdentity++;
      continue;
    }
    if (byKey.has(recordKey)) deduped++;
    byKey.set(recordKey, { recordKey, values, raw });
  }

  return {
    records: [...byKey.values()],
    extracted: rawRecords.length,
    rejectedRequired,
    rejectedIdentity,
    deduped,
  };
}

/** Convenience wrapper returning only the records. */
export function mapResponse(root: unknown, schema: DatasetSchema): MappedRecord[] {
  return mapResponseDetailed(root, schema).records;
}

/** Structural description of a JSON payload's paths, for the mapping UI. */
export interface FieldCandidate {
  path: string;
  type: "string" | "number" | "boolean" | "object" | "array" | "null";
}

/** Enumerate selectable source paths (depth-limited) from a sample payload. */
export function describeFields(value: unknown, maxDepth = 5): FieldCandidate[] {
  const out: FieldCandidate[] = [];
  const walk = (node: unknown, path: string, depth: number) => {
    if (out.length > 500 || depth > maxDepth) return;
    if (Array.isArray(node)) {
      out.push({ path, type: "array" });
      if (node.length > 0) walk(node[0], `${path}[*]`, depth + 1);
      return;
    }
    if (isRecord(node)) {
      out.push({ path, type: "object" });
      for (const [key, child] of Object.entries(node)) {
        walk(child, path === "$" ? key : `${path}.${key}`, depth + 1);
      }
      return;
    }
    out.push({
      path,
      type:
        node === null
          ? "null"
          : typeof node === "number"
            ? "number"
            : typeof node === "boolean"
              ? "boolean"
              : "string",
    });
  };
  walk(value, "$", 0);
  // Drop the synthetic root entry — callers map fields, not the whole payload.
  return out.filter((f) => f.path !== "$");
}
