// ── Table presentation ────────────────────────────────────────────────────────
//
// Financial tables read left-to-right, so numbers belong on the right and text
// on the left. The contract lets the planner choose an alignment; when it does
// not, this module infers it from the DATA (never from the column label alone)
// and formats raw numbers with locale separators. Numeric strings are left
// exactly as written: they may carry a currency, a percent sign or a magnitude
// suffix that formatting must not guess at.

import { inlineText, isNegativeValue, isNumericText, parseInline } from '@/lib/chat/markdown';
import type { TableCell } from './contract';

export type TableAlign = 'left' | 'center' | 'right';

function textOf(cell: TableCell): string {
  if (cell == null) return '';
  if (typeof cell === 'boolean') return cell ? 'yes' : 'no';
  return String(cell);
}

/** The numeric value of a cell, accepting formatted financial strings. */
export function numericCellValue(cell: TableCell): number | null {
  if (typeof cell === 'number') return Number.isFinite(cell) ? cell : null;
  if (typeof cell !== 'string') return null;
  const plain = inlineText(parseInline(cell));
  if (!isNumericText(plain)) return null;
  const n = Number(plain.replace(/[()$€£¥,%KMBT\s]/gi, ''));
  if (!Number.isFinite(n)) return null;
  return isNegativeValue(plain) ? -Math.abs(n) : n;
}

/** Locale-format a raw numeric cell; strings keep their supplied formatting. */
export function formatNumericCell(cell: TableCell): string | null {
  if (typeof cell !== 'number' || !Number.isFinite(cell)) return null;
  return cell.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

/**
 * The alignment for one column: an explicit choice wins; otherwise a column
 * whose populated cells are numeric is right-aligned.
 */
export function resolveColumnAlign(
  column: { align?: TableAlign },
  rows: ReadonlyArray<Record<string, TableCell>>,
  key: string,
): TableAlign {
  if (column.align) return column.align;
  let numeric = 0;
  let populated = 0;
  for (const row of rows) {
    const cell = row[key];
    if (cell == null || textOf(cell).trim() === '') continue;
    populated += 1;
    if (numericCellValue(cell) != null) numeric += 1;
  }
  return populated > 0 && numeric / populated >= 0.8 ? 'right' : 'left';
}

/** True when a label names a P&L/loss column (used for compact tone hints). */
export function isLossColumn(label: string): boolean {
  return /\b(loss|drawdown|p&l|pnl)\b/i.test(label);
}
