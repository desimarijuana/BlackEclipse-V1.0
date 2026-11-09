'use client';

// Market-news pagination footer. Extracted from `market-news.tsx` (which sits
// on the line budget) so the page can offer: windowed page numbers, a typed
// "go to page" box, and a typed cards-per-page control while the news API
// caps `limit` at MAX_PER_PAGE.

import { useEffect, useState, type ReactNode } from 'react';
import { PageSizeInput, pageNumbers } from '@/components/ui/pagination';

function PageJump({ page, pageCount, onGo }: {
  page: number;
  pageCount: number;
  onGo: (page: number) => void;
}) {
  const [draft, setDraft] = useState(String(page));
  useEffect(() => { setDraft(String(page)); }, [page]);

  const commit = () => {
    const n = Math.floor(Number(draft));
    if (!Number.isFinite(n) || n < 1) { setDraft(String(page)); return; }
    const next = Math.min(pageCount, Math.max(1, n));
    setDraft(String(next));
    if (next !== page) onGo(next);
  };

  return (
    <label className="flex items-center gap-1.5 ml-1">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">Go to</span>
      <input
        type="number"
        min={1}
        max={pageCount}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }}
        className="w-14 h-8.5 rounded-lg border border-border/30 bg-accent/30 px-2 font-mono text-[11px] text-foreground focus:outline-none focus:border-primary/40"
        aria-label={`Go to page (1–${pageCount})`}
      />
    </label>
  );
}

export function NewsPagination({
  page,
  totalPages,
  totalItems,
  perPage,
  maxPerPage,
  onPage,
  onPerPage,
}: {
  page: number;
  totalPages: number;
  totalItems: number;
  perPage: number;
  maxPerPage: number;
  onPage: (page: number) => void;
  onPerPage: (perPage: number) => void;
}) {
  const pageBtn = (n: number, active: boolean) => (
    <button
      key={n}
      onClick={() => onPage(n)}
      aria-current={active ? 'page' : undefined}
      className={`h-8.5 min-w-[34px] px-2 rounded-lg text-[12px] font-mono font-semibold cursor-pointer transition-all border ${
        active
          ? 'bg-primary/15 text-primary border-primary/40 shadow-[0_0_10px_rgba(139,92,246,0.15)]'
          : 'bg-accent/30 text-muted-foreground border-border/30 hover:border-primary/30 hover:text-foreground'
      }`}
    >
      {n}
    </button>
  );

  const navBtn = (label: string, target: number, disabled: boolean, arrow: ReactNode) => (
    <button
      onClick={() => !disabled && onPage(target)}
      disabled={disabled}
      className="h-8.5 px-3 rounded-lg text-[12px] font-semibold cursor-pointer transition-all border inline-flex items-center gap-1.5 bg-accent/30 text-muted-foreground border-border/30 hover:border-primary/30 hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-border/30 disabled:hover:text-muted-foreground"
    >
      {arrow} {label}
    </button>
  );

  return (
    <div className="flex flex-col lg:flex-row items-center justify-between gap-3 mt-8 p-4 glass-card-subtle border border-border/10 rounded-2xl font-mono select-none">
      <div className="flex flex-wrap items-center justify-center gap-3 text-[11px] text-muted-foreground order-2 lg:order-1">
        <span>
          Showing page <span className="text-foreground font-bold">{page}</span> of{' '}
          <span className="text-foreground font-bold">{totalPages}</span>
          {totalItems > 0 && <> · <span className="text-foreground font-bold">{totalItems}</span> articles</>}
        </span>
        <PageSizeInput
          pageSize={perPage}
          max={maxPerPage}
          onCommit={onPerPage}
          label="Cards per page"
        />
      </div>

      <div className="flex flex-wrap items-center justify-center gap-1.5 order-1 lg:order-2">
        {navBtn('Prev', page - 1, page <= 1, <span aria-hidden>&larr;</span>)}
        {pageNumbers(page, totalPages).map((n, idx) =>
          n === '…' ? (
            <span key={`ellipsis-${idx}`} className="h-8.5 min-w-[24px] inline-flex items-center justify-center text-muted-foreground/50 text-[12px]">…</span>
          ) : (
            pageBtn(n, n === page)
          ),
        )}
        {navBtn('Next', page + 1, page >= totalPages, <span aria-hidden>&rarr;</span>)}
        <PageJump page={page} pageCount={totalPages} onGo={onPage} />
      </div>
    </div>
  );
}
