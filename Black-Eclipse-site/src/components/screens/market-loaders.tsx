'use client';

import { useState, useEffect } from 'react';

// ── Screener loading primitives ─────────────────────────────────────────────
// Extracted from market-overview.tsx (memory/simplicity standing goal). Used
// by the screener tables, the Global Markets cards, and the full-page loaders.

// Quiet ASCII-style progress line. Per-section data loads use this instead of
// multiple dot grids so the page never floods with spinners.
export function TableLoading({ pct, label }: { pct: number; label: string }) {
  const [currentPct, setCurrentPct] = useState(pct);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (currentPct < 95) {
      timer = setInterval(() => {
        setCurrentPct(prev => Math.min(95, prev + Math.max(0.5, (95 - prev) * 0.05)));
      }, 300);
    } else if (pct === 100) {
      setCurrentPct(100);
    }
    return () => clearInterval(timer);
  }, [pct, currentPct]);

  return (
    <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground/70">
      <span className="w-4 h-4 rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70 animate-spin" aria-hidden />
      <span className="font-bold">{Math.floor(currentPct)}%</span>
      {label && <span className="truncate">· {label}</span>}
    </div>
  );
}

export function TableSkeleton({ cols = 11, rows = 6 }: { cols?: number; rows?: number }) {
  return (
    <tr>
      <td colSpan={cols} className="p-6">
        <div className="flex items-center justify-center">
          <TableLoading pct={Math.min(95, 30 + rows * 8)} label="loading table" />
        </div>
      </td>
    </tr>
  );
}
