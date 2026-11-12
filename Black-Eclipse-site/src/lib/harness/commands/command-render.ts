// ─── Command result rendering ────────────────────────────────────────────────
// Builds the structured (`eclipse-response`) blocks a command hands back to the
// chat renderer, plus the fenced envelope string. Pure: no execution, no I/O.
// Blocks are validated against the response contract before they are emitted, so
// a command can never hand the renderer a malformed block.

import {
  RESPONSE_FENCE_LANGUAGE,
  RESPONSE_SCHEMA_VERSION,
  ResponseBlockSchema,
  type ResponseBlock,
  type TableColumn,
} from "@/lib/response/contract";

export function heading(text: string, level: 1 | 2 | 3 | 4 = 2): ResponseBlock {
  return { type: "heading", text, level };
}

export function markdown(md: string): ResponseBlock {
  return { type: "markdown", markdown: md };
}

export function callout(
  tone: "info" | "note" | "success" | "warning" | "danger",
  title: string,
  md: string,
): ResponseBlock {
  return { type: "callout", tone, title, markdown: md };
}

export function dataTable(
  title: string,
  columns: TableColumn[],
  rows: Array<Record<string, unknown>>,
): ResponseBlock {
  const safeColumns: TableColumn[] = columns.map((c) => ({
    key: c.key,
    label: c.label,
    ...(c.align ? { align: c.align } : {}),
  }));
  const safeRows = rows.map((row) => {
    const out: Record<string, string | number | boolean | null> = {};
    for (const col of safeColumns) {
      const raw = row[col.key];
      out[col.key] =
        raw === null || raw === undefined
          ? null
          : typeof raw === "number" || typeof raw === "boolean"
            ? raw
            : String(raw).slice(0, 2000);
    }
    return out;
  });
  return {
    type: "data_table",
    title,
    columns: safeColumns,
    rows: safeRows,
    filterable: true,
    sortable: true,
    pageSize: 25,
  };
}

export function keyValue(
  title: string,
  items: Array<{ label: string; value: string | number; hint?: string }>,
): ResponseBlock {
  return {
    type: "key_value",
    title,
    items: items.map((item) => ({
      label: item.label.slice(0, 500),
      value: typeof item.value === "number" ? item.value : String(item.value).slice(0, 500),
      ...(item.hint ? { hint: item.hint.slice(0, 500) } : {}),
    })),
  };
}

/**
 * Serialize blocks into a fenced `eclipse-response` envelope. Blocks that fail
 * validation are dropped (with the rest kept) so one bad block never costs the
 * whole result.
 */
export function fenceEnvelope(blocks: ResponseBlock[], title?: string): string {
  const valid = blocks
    .map((block) => ResponseBlockSchema.safeParse(block))
    .filter((r): r is { success: true; data: ResponseBlock } => r.success)
    .map((r) => r.data);
  const payload = {
    schemaVersion: RESPONSE_SCHEMA_VERSION,
    ...(title ? { title } : {}),
    blocks: valid,
  };
  return "```" + RESPONSE_FENCE_LANGUAGE + "\n" + JSON.stringify(payload) + "\n```";
}
