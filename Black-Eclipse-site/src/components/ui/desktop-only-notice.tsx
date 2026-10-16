'use client';

// ── DesktopOnlyNotice — "best on desktop" banner for heavy editor screens ────
// UI Builder, ML Lab, Factor Lab and Backtest are dense, pointer-driven editor
// surfaces. On phones we show a dismissible, non-blocking notice (the page still
// renders read-only) rather than hiding the tab entirely. `md:hidden` so it
// never appears on tablet/desktop.

import { useState } from 'react';
import { Monitor, X } from '@/lib/icons';

export function DesktopOnlyNotice({ title }: { title: string }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <div className="mb-3 flex items-start gap-2 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2.5 text-[11px] text-amber-200 md:hidden">
      <Monitor size={15} className="mt-0.5 shrink-0" />
      <p className="min-w-0 flex-1 leading-relaxed">
        <span className="font-semibold">{title}</span> is built for a larger screen — some editing
        controls are limited on mobile.
      </p>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="touch-target -mr-1 -mt-1 flex items-center justify-center rounded-lg text-amber-200/70 hover:text-amber-100"
      >
        <X size={15} />
      </button>
    </div>
  );
}
