"use client";

// Shared pagination — one consistent footer for any bounded-by-page list.
//
// Sibling screens (market tables, news) each rolled their own pagination math.
// This centralizes it so a long list (learning queue, executions, relations)
// never overflows a page: it slices a client-side array and renders a compact
// glass footer with a page-size selector.
//
// Client-side pagination is deliberate here: these lists are already fully
// loaded and bounded (the backend caps them), so there is no second fetch and
// no risk of paging past the server's window.

import { useEffect, useId, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];

/** Upper bounds the backend accepts for a single page (artifacts = 200). */
export const DEFAULT_MAX_PAGE_SIZE = 200;

/**
 * Typed page-size control: presets are offered through a datalist, but the
 * number can be typed directly (clamped to 1…max). It only commits on blur or
 * Enter so typing a value never fires a request per keystroke.
 */
export function PageSizeInput({
  pageSize,
  onCommit,
  max = DEFAULT_MAX_PAGE_SIZE,
  label = "Per page",
  className,
}: {
  pageSize: number;
  onCommit: (size: number) => void;
  max?: number;
  label?: string;
  className?: string;
}) {
  const listId = useId();
  const [draft, setDraft] = useState(String(pageSize));

  useEffect(() => { setDraft(String(pageSize)); }, [pageSize]);

  const commit = () => {
    const parsed = Math.floor(Number(draft));
    if (!Number.isFinite(parsed) || parsed < 1) {
      setDraft(String(pageSize));
      return;
    }
    const next = Math.min(max, Math.max(1, parsed));
    setDraft(String(next));
    if (next !== pageSize) onCommit(next);
  };

  return (
    <label className={cn("flex items-center gap-1.5", className)}>
      <span className="uppercase tracking-widest font-bold text-muted-foreground/80">{label}</span>
      <input
        type="number"
        min={1}
        max={max}
        list={listId}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); commit(); }
        }}
        className="w-14 rounded-lg border border-border/30 bg-transparent px-1.5 py-0.5 font-mono text-[10px] font-bold text-foreground focus:outline-none"
        aria-label={`${label} (1–${max})`}
      />
      <datalist id={listId}>
        {PAGE_SIZE_OPTIONS.filter((size) => size <= max).map((size) => (
          <option key={size} value={size} />
        ))}
      </datalist>
    </label>
  );
}

/** Windowed page numbers: 1 … (p-1) p (p+1) … last. */
export function pageNumbers(page: number, pageCount: number, radius = 1): (number | "…")[] {
  const out: (number | "…")[] = [];
  const push = (n: number | "…") => {
    if (out[out.length - 1] !== n) out.push(n);
  };
  push(1);
  if (page - radius > 2) push("…");
  for (let i = Math.max(2, page - radius); i <= Math.min(pageCount - 1, page + radius); i++) push(i);
  if (page + radius < pageCount - 1) push("…");
  if (pageCount > 1) push(pageCount);
  return out;
}

export interface Pagination<T> {
  /** The slice for the current page. */
  pageItems: T[];
  page: number;
  pageCount: number;
  total: number;
  pageSize: number;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  /** 1-based index of the first item on this page (0 when empty). */
  from: number;
  /** 1-based index of the last item on this page (0 when empty). */
  to: number;
}

/**
 * Client-side pagination over an already-loaded array. The page is clamped when
 * the underlying list shrinks (e.g. after an item is removed), so the view never
 * ends up on an empty page.
 */
export function usePagination<T>(items: readonly T[], initialPageSize: PageSize = 25): Pagination<T> {
  const [page, setPageState] = useState(1);
  const [pageSize, setPageSizeState] = useState<number>(initialPageSize);

  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  // Clamp when the list shrinks past the current page.
  useEffect(() => {
    setPageState((current) => Math.min(current, pageCount));
  }, [pageCount]);

  const pageItems = useMemo(
    () => items.slice((page - 1) * pageSize, page * pageSize),
    [items, page, pageSize],
  );

  const setPage = (next: number) => setPageState(Math.min(Math.max(1, next), pageCount));
  const setPageSize = (size: number) => {
    setPageSizeState(size);
    setPageState(1);
  };

  return {
    pageItems, page, pageCount, total, pageSize, setPage, setPageSize,
    from: total === 0 ? 0 : (page - 1) * pageSize + 1,
    to: Math.min(page * pageSize, total),
  };
}

/** Compact pagination footer. Renders nothing when there is a single page. */
export function PaginationFooter<T>({
  pagination,
  label = "items",
  maxPageSize = DEFAULT_MAX_PAGE_SIZE,
  className,
}: {
  pagination: Pagination<T>;
  label?: string;
  maxPageSize?: number;
  className?: string;
}) {
  const { page, pageCount, total, pageSize, setPage, setPageSize, from, to } = pagination;
  if (total === 0) return null;

  return (
    <div className={cn("mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border/10 pt-3", className)}>
      <div className="flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
        <span>
          Showing <span className="font-mono font-semibold text-foreground">{from}</span>–
          <span className="font-mono font-semibold text-foreground">{to}</span> of{" "}
          <span className="font-mono font-semibold text-foreground">{total}</span> {label}
        </span>
        <PageSizeInput pageSize={pageSize} max={maxPageSize} onCommit={setPageSize} />
      </div>

      {pageCount > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-1.5">
          <Button variant="outline" size="sm" className="h-7 cursor-pointer rounded-lg px-2"
            onClick={() => setPage(1)} disabled={page === 1} aria-label="First page">
            <ChevronLeft size={12} /><ChevronLeft size={12} className="-ml-2" />
          </Button>
          <Button variant="outline" size="sm" className="h-7 cursor-pointer rounded-lg px-2"
            onClick={() => setPage(page - 1)} disabled={page === 1} aria-label="Previous page">
            <ChevronLeft size={12} />
          </Button>
          {pageNumbers(page, pageCount).map((n, idx) =>
            n === "…" ? (
              <span key={`gap-${idx}`} className="px-1 font-mono text-[10px] text-muted-foreground/50">…</span>
            ) : (
              <button
                key={n}
                type="button"
                onClick={() => setPage(n)}
                aria-current={n === page ? "page" : undefined}
                className={cn(
                  "h-7 min-w-7 cursor-pointer rounded-lg border px-1.5 font-mono text-[10px] font-bold transition-colors",
                  n === page
                    ? "border-primary/40 bg-primary/15 text-primary"
                    : "border-border/30 bg-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {n}
              </button>
            ),
          )}
          <Button variant="outline" size="sm" className="h-7 cursor-pointer rounded-lg px-2"
            onClick={() => setPage(page + 1)} disabled={page >= pageCount} aria-label="Next page">
            <ChevronRight size={12} />
          </Button>
          <Button variant="outline" size="sm" className="h-7 cursor-pointer rounded-lg px-2"
            onClick={() => setPage(pageCount)} disabled={page >= pageCount} aria-label="Last page">
            <ChevronRight size={12} /><ChevronRight size={12} className="-ml-2" />
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * Server-side pagination footer. Use when the API returns `total` and a page,
 * rather than loading every row into the browser. `count` is the number of rows
 * on the current page, so the "showing X–Y" range stays honest after a delete.
 */
export function ServerPaginationFooter({
  total,
  limit,
  offset,
  count,
  onOffset,
  onLimit,
  maxPageSize = DEFAULT_MAX_PAGE_SIZE,
  numbered = false,
  label = "items",
  disabled = false,
  className,
}: {
  total: number;
  limit: number;
  offset: number;
  count: number;
  onOffset: (offset: number) => void;
  /** When provided, renders the typed page-size control. */
  onLimit?: (limit: number) => void;
  maxPageSize?: number;
  /** Render windowed page-number buttons between the arrows. */
  numbered?: boolean;
  label?: string;
  disabled?: boolean;
  className?: string;
}) {
  if (total === 0) return null;
  const pageCount = Math.max(1, Math.ceil(total / Math.max(1, limit)));
  const page = Math.min(pageCount, Math.floor(offset / Math.max(1, limit)) + 1);
  const from = count === 0 ? 0 : offset + 1;
  const to = Math.min(offset + count, total);

  return (
    <div className={cn("mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border/10 pt-3", className)}>
      <div className="flex flex-wrap items-center gap-3 text-[10px] text-muted-foreground">
        <span>
          Showing <span className="font-mono font-semibold text-foreground">{from}</span>–
          <span className="font-mono font-semibold text-foreground">{to}</span> of{" "}
          <span className="font-mono font-semibold text-foreground">{total}</span> {label}
        </span>
        {onLimit ? <PageSizeInput pageSize={limit} max={maxPageSize} onCommit={onLimit} /> : null}
      </div>
      {pageCount > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-1.5">
          <Button variant="outline" size="sm" className="h-7 cursor-pointer rounded-lg px-2"
            onClick={() => onOffset(0)} disabled={disabled || page === 1} aria-label="First page">
            <ChevronLeft size={12} /><ChevronLeft size={12} className="-ml-2" />
          </Button>
          <Button variant="outline" size="sm" className="h-7 cursor-pointer rounded-lg px-2"
            onClick={() => onOffset(Math.max(0, offset - limit))} disabled={disabled || page === 1}
            aria-label="Previous page">
            <ChevronLeft size={12} />
          </Button>
          {numbered ? (
            pageNumbers(page, pageCount).map((n, idx) =>
              n === "…" ? (
                <span key={`gap-${idx}`} className="px-1 font-mono text-[10px] text-muted-foreground/50">…</span>
              ) : (
                <button
                  key={n}
                  type="button"
                  onClick={() => onOffset((n - 1) * limit)}
                  disabled={disabled}
                  aria-current={n === page ? "page" : undefined}
                  className={cn(
                    "h-7 min-w-7 cursor-pointer rounded-lg border px-1.5 font-mono text-[10px] font-bold transition-colors disabled:cursor-not-allowed",
                    n === page
                      ? "border-primary/40 bg-primary/15 text-primary"
                      : "border-border/30 bg-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {n}
                </button>
              ),
            )
          ) : (
            <span className="px-2 font-mono text-[10px] font-bold text-foreground">
              {page} / {pageCount}
            </span>
          )}
          <Button variant="outline" size="sm" className="h-7 cursor-pointer rounded-lg px-2"
            onClick={() => onOffset(offset + limit)} disabled={disabled || page >= pageCount}
            aria-label="Next page">
            <ChevronRight size={12} />
          </Button>
          <Button variant="outline" size="sm" className="h-7 cursor-pointer rounded-lg px-2"
            onClick={() => onOffset((pageCount - 1) * limit)} disabled={disabled || page >= pageCount}
            aria-label="Last page">
            <ChevronRight size={12} /><ChevronRight size={12} className="-ml-2" />
          </Button>
        </div>
      )}
    </div>
  );
}
