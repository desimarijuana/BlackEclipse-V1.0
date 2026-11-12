// ── Response-contract bridge capability ─────────────────────────────────────────
// Exposes the Interactive Response Engine's block contract to the Python runtime
// through the read-only data bridge, so the model can do what it could not before:
//   * `op: "schema"`   — the EXACT field names for every block type, derived LIVE
//                        from the zod contract (single source of truth; no copy),
//                        plus the live icon-key vocabulary (`iconKeys`) for the
//                        semantic `icon` fields.
//   * `op: "validate"` — validate a drafted answer/fence BEFORE emitting it and get
//                        per-block errors back (the read-back for the response format).
//
// Read-only and pure: it parses the caller's text with the SAME parser the chat
// renderer uses. Nothing here executes, fetches or persists anything.
//
// SERVER-SAFE imports only: the icon vocabulary comes from
// `@/lib/response/icon-vocabulary` (pure data), NOT `./icons` (client React
// icon set) — the latter crashes this route under the react-server condition.

import { parseResponsePayload, ResponseBlockSchema } from "@/lib/response/contract";
import { splitResponseSegments } from "@/lib/response/parse";
import { finalizeFenceSource } from "@/lib/response/finalize";
import { RESPONSE_ICON_KEYS } from "@/lib/response/icon-vocabulary";
import { chartBlockWarning } from "@/lib/response/chart-capabilities";
import type { DataBridgeResult } from "@/lib/harness/data-bridge/data-bridge-types";

const MAX_VALIDATE_CHARS = 200_000;

type FieldInfo = { name: string; required: boolean; kind: string; itemFields?: string[];
  /**
   * For array kinds: the element object's fields, one level deeper. The
   * SCENE's mark vocabulary lives here (`panels` -> `marks` -> a mark's
   * fields), so the model can see every chart the engine can draw.
   */
  itemDetail?: FieldInfo[] };

/** Unwrap optional/default/nullable wrappers to the underlying schema. */
function unwrap(schema: unknown): unknown {
  let s = schema;
  for (let i = 0; i < 5; i++) {
    const d = (s as { def?: { type?: string; innerType?: unknown } })?.def;
    if (!d || !["optional", "default", "nullable", "readonly", "catch"].includes(d.type ?? "")) break;
    if (d.innerType === undefined) break;
    s = d.innerType;
  }
  return s;
}

function defOf(schema: unknown): Record<string, unknown> | undefined {
  return (schema as { def?: Record<string, unknown> })?.def;
}

/** A compact, human-readable kind for one field (arrays described one level deep). */
function kindOf(schema: unknown): string {
  const bare = unwrap(schema);
  const d = defOf(bare);
  const t = typeof d?.type === "string" ? d.type : "unknown";
  try {
    switch (t) {
      case "enum": {
        const entries = d?.entries as Record<string, unknown> | undefined;
        return entries ? `enum(${Object.keys(entries).join("|")})` : "enum";
      }
      case "array":
        return `${kindOf(d?.element)}[]`;
      default:
        return t;
    }
  } catch {
    return t;
  }
}

interface BlockStats {
  blockTypes: Record<string, number>;
  refs: number;
  computedRefs: number;
}

/** Count block types and figure bindings (recursing into container blocks). */
function countBlockStats(blocks: unknown[]): BlockStats {
  const blockTypes: Record<string, number> = {};
  let refs = 0;
  let computedRefs = 0;
  const scanValues = (value: unknown): void => {
    if (Array.isArray(value)) {
      value.forEach(scanValues);
    } else if (value && typeof value === "object") {
      const record = value as Record<string, unknown>;
      if (typeof record.$ref === "string") refs += 1;
      if (typeof record.$computed === "string") computedRefs += 1;
      Object.values(record).forEach(scanValues);
    }
  };
  const visit = (block: unknown): void => {
    if (!block || typeof block !== "object") return;
    const b = block as Record<string, unknown>;
    if (typeof b.type === "string") blockTypes[b.type] = (blockTypes[b.type] ?? 0) + 1;
    scanValues(b);
    if (Array.isArray(b.blocks)) b.blocks.forEach(visit);
    if (Array.isArray(b.tabs)) (b.tabs as { blocks?: unknown[] }[]).forEach((t) => (t.blocks ?? []).forEach(visit));
    if (Array.isArray(b.sections)) (b.sections as { blocks?: unknown[] }[]).forEach((s) => (s.blocks ?? []).forEach(visit));
    if (Array.isArray(b.slides)) (b.slides as { blocks?: unknown[] }[]).forEach((s) => (s.blocks ?? []).forEach(visit));
  };
  blocks.forEach(visit);
  return { blockTypes, refs, computedRefs };
}

/**
 * Describe an array's ELEMENT object: its field names, and (one level deeper)
 * the fields of an array-of-objects inside it.
 *
 * The depth matters: a chart SCENE is `panels` -> `marks` -> a mark's fields,
 * and the mark's `type` is the vocabulary of every chart the engine can draw.
 * Without that level the model could see that a scene exists but not what a
 * mark may be.
 */
function describeItem(element: unknown, depth = 0): { names: string[]; detail?: FieldInfo[] } {
  const elementDef = defOf(element);
  if (elementDef?.type !== "object") return { names: [] };
  const shape = (element as { shape?: Record<string, unknown> }).shape ?? {};
  // NOTE: a `type` field is NOT skipped here. At the BLOCK level it is the
  // discriminator (skipped by the caller), but inside a scene it is the
  // MARK's primitive - the whole vocabulary of charts the engine can draw.
  const names = Object.keys(shape);
  if (depth <= 0) return { names };
  const detail: FieldInfo[] = [];
  for (const [name, schema] of Object.entries(shape)) {
    const bare = unwrap(schema);
    const bareDef = defOf(bare);
    let itemFields: string[] | undefined;
    let itemDetail: FieldInfo[] | undefined;
    if (bareDef?.type === "array") {
      const nested = describeItem(unwrap(bareDef.element), depth - 1);
      itemFields = nested.names;
      itemDetail = nested.detail;
    }
    detail.push({
      name,
      required: !(schema as { isOptional?: () => boolean }).isOptional?.(),
      kind: kindOf(schema),
      ...(itemFields ? { itemFields } : {}),
      ...(itemDetail ? { itemDetail } : {}),
    });
  }
  return { names, detail };
}

function describeOption(option: unknown): { type: string; fields: FieldInfo[] } {
  const shape = ((option as { shape?: Record<string, unknown> }).shape ?? {}) as Record<string, unknown>;
  const typeDef = defOf(shape.type);
  const values = typeDef?.values as unknown[] | undefined;
  const type = String(typeDef?.value ?? values?.[0] ?? "?");
  const fields: FieldInfo[] = [];
  for (const [name, schema] of Object.entries(shape)) {
    if (name === "type") continue;
    const bare = unwrap(schema);
    const bareDef = defOf(bare);
    let itemFields: string[] | undefined;
    let itemDetail: FieldInfo[] | undefined;
    if (bareDef?.type === "array") {
      const element = unwrap(bareDef.element);
      const described = describeItem(element, 2);
      itemFields = described.names;
      itemDetail = described.detail;
    }
    fields.push({
      name,
      required: !(schema as { isOptional?: () => boolean }).isOptional?.(),
      kind: kindOf(schema),
      ...(itemFields ? { itemFields } : {}),
      ...(itemDetail ? { itemDetail } : {}),
    });
  }
  return { type, fields };
}

/** The live field map for every registered block type (derived from the contract). */
export function describeResponseBlocks(): { type: string; fields: FieldInfo[] }[] {
  const union = ResponseBlockSchema as unknown as { options?: unknown[] };
  return (union.options ?? []).map(describeOption);
}

/**
 * The bridge capability handler. `params.op` selects the operation; anything
 * unrecognized returns an explicit ERROR rather than a fabricated result.
 */
export async function responseContractCapability(
  params: Record<string, unknown>,
): Promise<DataBridgeResult> {
  const op = typeof params.op === "string" ? params.op : "";

  if (op === "schema") {
    const wanted = typeof params.block_type === "string" ? params.block_type.trim() : "";
    const blocks = describeResponseBlocks();
    return {
      status: "OK",
      op,
      blocks: wanted ? blocks.filter((b) => b.type === wanted) : blocks,
      // The live icon vocabulary for every `icon` field, derived from the same
      // registry the renderer resolves against (cannot drift from it).
      iconKeys: [...RESPONSE_ICON_KEYS],
    };
  }

  if (op === "validate") {
    const markdown = typeof params.markdown === "string" ? params.markdown : "";
    if (!markdown.trim()) return { status: "UNAVAILABLE", error: "markdown is required" };
    if (markdown.length > MAX_VALIDATE_CHARS) {
      return { status: "UNAVAILABLE", error: "payload too large to validate" };
    }
    // Accept either a full message containing the fence or the bare JSON payload.
    const segment = splitResponseSegments(markdown).find((s) => s.kind === "response");
    if (!segment && !markdown.trim().startsWith("{")) {
      return {
        status: "OK",
        op,
        ok: false,
        error: "no eclipse-response fence found in the text and the text is not a bare JSON payload",
        blocks: [],
        diagnostics: [],
      };
    }
    const source = segment ? segment.source.trim() : markdown.trim();
    let value: unknown;
    try {
      value = JSON.parse(source);
    } catch (error) {
      const message = error instanceof Error ? error.message : "parse error";
      return { status: "OK", op, ok: false, error: `malformed JSON: ${message}`, blocks: [], diagnostics: [] };
    }
    const parsed = parseResponsePayload(value);
    const errors = parsed.diagnostics.filter((d) => d.severity === "error");
    const diagByIndex = new Map(
      errors.filter((d) => d.blockIndex != null).map((d) => [d.blockIndex as number, `${d.code}: ${d.message}`]),
    );
    const envelopeError = errors.find((d) => d.blockIndex == null);
    const blocks = parsed.blocks.map((block, index) => {
      // A chart can be schema-valid and still not drawable (empty series, a
      // mark the renderer does not have). Validate the MAPPED spec too, so
      // "validated" means "will render" rather than "will parse".
      const chartWarning = block.type === "chart" ? chartBlockWarning(block) : null;
      return {
        index,
        type: block.type === "unknown" ? (block as { declaredType?: string }).declaredType ?? "unknown" : block.type,
        ok: block.type !== "unknown" && !chartWarning,
        error: diagByIndex.get(index) ?? chartWarning ?? null,
      };
    });
    return {
      status: "OK",
      op,
      ok: blocks.length > 0 && blocks.every((b) => b.ok) && !envelopeError,
      blockCount: blocks.length,
      blocks,
      diagnostics: errors.map((d) => ({ code: d.code, message: d.message, blockIndex: d.blockIndex ?? null })),
    };
  }

  if (op === "finalize") {
    // Phase 4 telemetry read-back: run the answer through the SAME render
    // chokepoint the client uses (`finalizeFenceSource`) and return the render
    // OUTCOME — how many blocks had to be repaired or degraded, and which block
    // types. This is what makes the drift rate measurable and feeds new rules.
    const markdown = typeof params.markdown === "string" ? params.markdown : "";
    if (!markdown.trim()) return { status: "UNAVAILABLE", error: "markdown is required" };
    if (markdown.length > MAX_VALIDATE_CHARS) {
      return { status: "UNAVAILABLE", error: "payload too large to finalize" };
    }
    const segment = splitResponseSegments(markdown).find((s) => s.kind === "response");
    if (!segment && !markdown.trim().startsWith("{")) {
      // No structured answer at all — nothing to measure.
      return { status: "OK", op, blocks: 0, repaired: 0, degraded: 0, repairedTypes: [], degradedTypes: [] };
    }
    const finalized = finalizeFenceSource(segment ? segment.source : markdown.trim());
    const records = finalized.degraded;
    const repairedRecords = records.filter((r) => r.code === "BLOCK_REPAIRED");
    const degradedRecords = records.filter((r) => r.code === "BLOCK_DEGRADED" || r.code === "MALFORMED_JSON");
    const unique = (values: (string | undefined)[]) => [...new Set(values.filter((v): v is string => Boolean(v)))];
    const stats = countBlockStats(finalized.response.blocks);
    return {
      status: "OK",
      op,
      blocks: finalized.response.blocks.length,
      repaired: repairedRecords.length,
      degraded: degradedRecords.length,
      repairedTypes: unique(repairedRecords.map((r) => r.declaredType)),
      degradedTypes: unique(degradedRecords.map((r) => r.declaredType ?? (r.code === "MALFORMED_JSON" ? "malformed" : "unknown"))),
      // Phase 6 telemetry: block-type histogram + figure-binding counts.
      blockTypes: stats.blockTypes,
      refs: stats.refs,
      computedRefs: stats.computedRefs,
      stateVars: finalized.response.state.length,
      computedVars: finalized.response.computed.length,
    };
  }

  return { status: "UNAVAILABLE", error: `unknown response_contract op: ${op || "(missing)"}` };
}
