'use client';

// ── Investor Eye — Heatmap quick toggle ──────────────────────────────────────
// A single, always-visible control for the severity-weighted event heatmap.
//
// The heatmap is also a chip in the full Layer Controller, but that strip is
// dense and easy to miss. This stands alone on the map surface so "where is the
// activity concentrated?" is one obvious click away on every Investor Eye
// surface (main screen, full-page map, dashboard widget).
//
// It writes the SAME store field the Layer Controller does, so the two are
// always in agreement.

import { Flame } from 'lucide-react';
import { useInvestorEyeStore } from '@/lib/investor-eye/store';
import { cn } from '@/lib/utils';

const HEATMAP_LAYER = 'event-heatmap';

export function HeatmapToggle({ className, showLabel = true }: { className?: string; showLabel?: boolean }) {
  const active = useInvestorEyeStore((s) => s.activeLayers.includes(HEATMAP_LAYER));
  const toggleLayer = useInvestorEyeStore((s) => s.toggleLayer);

  return (
    <button
      type="button"
      onClick={() => toggleLayer(HEATMAP_LAYER)}
      aria-pressed={active}
      title={
        active
          ? 'Hide the event heatmap'
          : 'Show the event heatmap — where events concentrate (2D map)'
      }
      className={cn(
        'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[10px] font-semibold transition-all cursor-pointer',
        active
          ? 'border-primary/40 bg-primary/15 text-primary'
          : 'border-white/15 dark:border-white/10 bg-accent/30 text-muted-foreground hover:border-primary/40 hover:text-primary',
        className,
      )}
    >
      <Flame size={12} />
      {showLabel && <span>Heatmap</span>}
    </button>
  );
}
