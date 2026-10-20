'use client';

// ── DataTableBlock — interactive table block ──────────────────────────────────
// Fully local interactions (no model calls): column sort, a text filter across
// all cells, and pagination. Copy serialises the *filtered + sorted* view to TSV.

import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, Copy, Check, Search } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { inlineText, isNegativeValue, isNumericText, isUnavailableText, parseInline } from '@/lib/chat/markdown';
import { renderInline } from '@/components/chat/markdown';
import {
  formatNumericCell,
  numericCellValue,
  resolveColumnAlign,
} from '@/lib/response/table-presentation';
import type { TableCell } from '@/lib/response/contract';

export interface DataTableBlockProps {
  title?: string;
  caption?: string;
  source?: string;
  asOf?: string;
  columns: { key: string; label: string; align?: 'left' | 'center' | 'right'; hint?: string }[];
  rows: Record<string, TableCell>[];
  filterable?: boolean;
  sortable?: boolean;
  pageSize?: number;
  compact?: boolean;
}

type SortState = { key: string; dir: 'asc' | 'desc' } | null;

function cellText(cell: TableCell): string {
  if (cell == null) return '';
  if (typeof cell === 'boolean') return cell ? 'yes' : 'no';
  if (typeof cell === 'number') return formatNumericCell(cell) ?? String(cell);
  return String(cell);
}

/** A cell's plain text with inline Markdown markers removed (for filter/sort/TSV). */
function plainText(cell: TableCell): string {
  return inlineText(parseInline(cellText(cell)));
}

function renderCell(cell: TableCell) {
  const text = cellText(cell);
  if (cell == null || (typeof cell === 'string' && isUnavailableText(text))) {
    return (
      <span className="rounded border border-border/50 bg-accent/20 px-1.5 py-0.5 text-[0.75em] font-medium uppercase tracking-wide text-muted-foreground/80">
        {cell == null ? 'UNAVAILABLE' : text}
      </span>
    );
  }
  // Cells may carry inline Markdown (the deterministic planner lifts GFM table
  // cells verbatim), so render it as real elements — **bold** must be bold.
  const nodes = parseInline(text);
  const plain = inlineText(nodes);
  const numeric = isNumericText(plain) || typeof cell === 'number';
  const negative = numeric && isNegativeValue(plain);
  return <span className={cn(numeric && 'tabular-nums', negative && 'text-rose-400/90')}>{renderInline(nodes)}</span>;
}

export function DataTableBlock({
  title,
  caption,
  source,
  asOf,
  columns,
  rows,
  filterable = true,
  sortable = true,
  pageSize = 25,
  compact = false,
}: DataTableBlockProps) {
  const [filter, setFilter] = useState('');
  const [sort, setSort] = useState<SortState>(null);
  const [page, setPage] = useState(0);
  const [copied, setCopied] = useState(false);

  // Right-align numeric columns unless the planner chose an alignment. This is
  // what makes a P&L or holdings table read as a financial table, not prose.
  const alignments = useMemo(
    () => Object.fromEntries(columns.map((col) => [col.key, resolveColumnAlign(col, rows, col.key)])),
    [columns, rows],
  );

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    let out = rows;
    if (q) {
      out = rows.filter((row) => columns.some((col) => plainText(row[col.key]).toLowerCase().includes(q)));
    }
    if (sort) {
      const { key, dir } = sort;
      const numeric = out.every((row) => numericCellValue(row[key]) != null || row[key] == null);
      out = [...out].sort((a, b) => {
        if (numeric) {
          const av = numericCellValue(a[key]) ?? -Infinity;
          const bv = numericCellValue(b[key]) ?? -Infinity;
          return dir === 'asc' ? av - bv : bv - av;
        }
        const av = plainText(a[key]).toLowerCase();
        const bv = plainText(b[key]).toLowerCase();
        return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      });
    }
    return out;
  }, [rows, columns, filter, sort]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(safePage * pageSize, safePage * pageSize + pageSize);

  const toggleSort = (key: string) => {
    if (!sortable) return;
    setSort((s) => (s?.key === key ? (s.dir === 'asc' ? { key, dir: 'desc' } : null) : { key, dir: 'asc' }));
  };

  const copyTsv = async () => {
    const header = columns.map((c) => inlineText(parseInline(c.label))).join('\t');
    const body = filtered.map((row) => columns.map((c) => plainText(row[c.key])).join('\t')).join('\n');
    try {
      await navigator.clipboard.writeText([header, body].join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="w-full">
      {(title || source || asOf) && (
        <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
          {title && <h4 className="text-sm font-semibold text-foreground">{title}</h4>}
          {(source || asOf) && (
            <span className="font-mono text-[10px] text-muted-foreground/60">
              {source}
              {source && asOf ? ' · ' : ''}
              {asOf}
            </span>
          )}
        </div>
      )}

      {(filterable || sortable) && rows.length > 3 && (
        <div className="mb-2 flex items-center gap-2">
          {filterable && (
            <label className="relative flex-1">
              <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
              <input
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value);
                  setPage(0);
                }}
                placeholder="Filter rows…"
                aria-label="Filter table rows"
                className="w-full rounded-lg border border-border/60 bg-card/60 py-1.5 pl-7 pr-2 text-[12px] text-foreground outline-none focus:ring-1 focus:ring-primary"
              />
            </label>
          )}
          <button
            type="button"
            onClick={() => void copyTsv()}
            className="flex items-center gap-1 rounded-lg border border-border/50 px-2 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title="Copy table as TSV"
          >
            {copied ? <Check size={11} /> : <Copy size={11} />}
            {copied ? 'Copied' : 'TSV'}
          </button>
        </div>
      )}

      <div className="glass-card-subtle w-full overflow-x-auto rounded-xl">
        <table className="w-full border-collapse text-left text-[13px]">
          <thead>
            <tr>
              {columns.map((col) => {
                const active = sort?.key === col.key;
                return (
                  <th
                    key={col.key}
                    scope="col"
                    title={col.hint}
                    className={cn(
                      'border-b border-white/10 bg-black/[0.03] px-3 py-2.5 text-[12.5px] font-semibold tracking-tight transition-colors dark:bg-white/[0.04]',
                      active ? 'text-primary' : 'text-foreground/75',
                      sortable && 'group/th cursor-pointer select-none hover:bg-black/[0.05] hover:text-foreground dark:hover:bg-white/[0.06]',
                    )}
                    style={{ textAlign: alignments[col.key] }}
                    onClick={() => toggleSort(col.key)}
                    aria-sort={active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : sortable ? 'none' : undefined}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      {renderInline(parseInline(col.label))}
                      {sortable && (
                        <span
                          className={cn(
                            'inline-flex h-3.5 w-3.5 items-center justify-center transition-opacity',
                            active ? 'text-primary opacity-100' : 'opacity-0 group-hover/th:opacity-60',
                          )}
                        >
                          {active ? (
                            sort!.dir === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                          ) : (
                            <ArrowUpDown size={11} />
                          )}
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, ri) => (
              <tr key={ri} className="border-b border-white/[0.06] last:border-0">
                {columns.map((col) => (
                  <td key={col.key} className={cn('px-3 align-top break-words', compact ? 'py-1.5' : 'py-2.5')} style={{ textAlign: alignments[col.key] }}>
                    {renderCell(row[col.key] ?? null)}
                  </td>
                ))}
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-xs italic text-muted-foreground/70">
                  {filtered.length === 0 ? 'No matching rows.' : 'No rows.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground/60">
          {caption ? `${caption} · ` : ''}
          {filtered.length} row{filtered.length === 1 ? '' : 's'}
        </span>
        {pageCount > 1 && (
          <div className="flex items-center gap-1 text-[11px]">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={safePage === 0}
              className="rounded px-2 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
            >
              Prev
            </button>
            <span className="tabular-nums text-muted-foreground/70">
              {safePage + 1} / {pageCount}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={safePage >= pageCount - 1}
              className="rounded px-2 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default DataTableBlock;
