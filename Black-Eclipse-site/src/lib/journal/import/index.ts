// ── Import layer — public API ─────────────────────────────────────────────────
// Parses raw CSV text, detects the format, normalizes rows to CreateTradeInput,
// and provides template downloads.

import { parseCsv } from "./csv";
import { detectFormat, normalizeRow, IMPORT_FORMATS, type ImportFormat } from "./normalize";
import type { CreateTradeInput } from "../data";

export * from "./csv";
export * from "./normalize";

export interface ParseResult {
  format: ImportFormat;
  rows: CreateTradeInput[];
  skipped: number;
}

/** Parse raw CSV text into normalized trade rows. */
export function parseImportText(text: string, forceFormat?: ImportFormat): ParseResult {
  const parsed = parseCsv(text);
  if (parsed.length === 0) return { format: "generic", rows: [], skipped: 0 };

  const header = Object.keys(parsed[0]);
  const format = forceFormat ?? detectFormat(header);

  const rows: CreateTradeInput[] = [];
  let skipped = 0;
  for (const row of parsed) {
    const normalized = normalizeRow(format, row);
    if (normalized) rows.push(normalized);
    else skipped++;
  }
  return { format, rows, skipped };
}

/** Build a downloadable template CSV for a format. */
export function buildTemplate(format: ImportFormat): string {
  const meta = IMPORT_FORMATS.find((f) => f.id === format) ?? IMPORT_FORMATS[0];
  return `${meta.templateHeader}\n${meta.templateRow}\n`;
}
