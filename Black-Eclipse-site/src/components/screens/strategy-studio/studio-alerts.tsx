'use client';

// ── Studio alerts ───────────────────────────────────────────────────────────
// One error banner and one notice banner, with the same precedence the screen
// used inline: an error hides the notice.

import React from 'react';
import { AlertTriangle } from '@/lib/icons';

export function StudioAlerts({
  error,
  notice,
}: {
  error: string | null;
  notice: string | null;
}) {
  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }
  if (!notice) return null;
  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-200">
      {notice}
    </div>
  );
}
