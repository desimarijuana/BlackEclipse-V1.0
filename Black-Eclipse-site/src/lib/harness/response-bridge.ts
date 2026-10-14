// ── Response-contract bridge capability ─────────────────────────────────────────
// Exposes the Interactive Response Engine's block contract to the Python runtime
// through the read-only data bridge, so the model can do what it could not before:
//   * `op: "schema"`   — the EXACT field names for every block type, derived LIVE
//                        from the zod contract (single source of truth; no copy).
//   * `op: "validate"` — validate a drafted answer/fence BEFORE emitting it and get
//                        per-block errors back (the read-back for the response format).
//
// Read-only and pure: it parses the caller's text with the SAME parser the chat
// renderer uses. Nothing here executes, fetches or persists anything.

import { parseResponsePayload, ResponseBlockSchema } from "@/lib/response/contract";
import { splitResponseSegments } from "@/lib/response/parse";

const MAX_VALIDATE_CHARS = 200_000;

type FieldInfo = { name: string; required: boolean; kind: string; itemFields?: string[] };

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
    if (bareDef?.type === "array") {
      const element = unwrap(bareDef.element);
      const elementDef = defOf(element);
      if (elementDef?.type === "object") {
        itemFields = Object.keys((element as { shape?: Record<string, unknown> }).shape ?? {}).filter(
          (k) => k !== "type",
        );
      }
    }
    fields.push({
      name,
      required: !(schema as { isOptional?: () => boolean }).isOptional?.(),
      kind: kindOf(schema),
      ...(itemFields ? { itemFields } : {}),
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
): Promise<Record<string, unknown>> {
  const op = typeof params.op === "string" ? params.op : "";

  if (op === "schema") {
    const wanted = typeof params.block_type === "string" ? params.block_type.trim() : "";
    const blocks = describeResponseBlocks();
    return {
      status: "OK",
      op,
      blocks: wanted ? blocks.filter((b) => b.type === wanted) : blocks,
    };
  }

  if (op === "validate") {
    const markdown = typeof params.markdown === "string" ? params.markdown : "";
    if (!markdown.trim()) return { status: "ERROR", error: "markdown is required" };
    if (markdown.length > MAX_VALIDATE_CHARS) {
      return { status: "ERROR", error: "payload too large to validate" };
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
    const blocks = parsed.blocks.map((block, index) => ({
      index,
      type: block.type === "unknown" ? (block as { declaredType?: string }).declaredType ?? "unknown" : block.type,
      ok: block.type !== "unknown",
      error: diagByIndex.get(index) ?? null,
    }));
    return {
      status: "OK",
      op,
      ok: blocks.length > 0 && blocks.every((b) => b.ok) && !envelopeError,
      blockCount: blocks.length,
      blocks,
      diagnostics: errors.map((d) => ({ code: d.code, message: d.message, blockIndex: d.blockIndex ?? null })),
    };
  }

  return { status: "ERROR", error: `unknown response_contract op: ${op || "(missing)"}` };
}
