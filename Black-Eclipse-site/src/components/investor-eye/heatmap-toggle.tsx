'use client';

// ── Investor Eye — Heatmap quick toggle ──────────────────────────────────────
// A single, always-visible control for the severity-weighted event heatmap.
//
// The heatmap is also a chip in the full Layer Controller, but that strip is
// dense and easy to miss. This stands alone beside the other map controls so
// "where is the activity concentrated?" is one obvious click away on every
// Investor Eye surface (main screen, full-page map, dashboard widget).
//
// It writes the SAME store field the Layer Controller does, so the two are
// always in agreement.
//
// `variant` matches the surrounding controls: `glass` is the Investor Eye
// header recipe (`glass-button`), `accent` is the dashboard widget's recipe
// (`bg-accent/30` + hairline border), so the toggle never looks bolted on.

import { Flame } from '@/lib/icons';
import { useInvestorEyeStore } from '@/lib/investor-eye/store';
import { cn } from '@/lib/utils';

const HEATMAP_LAYER = 'event-heatmap';

const VARIANTS = {
  glass: {
    base: 'glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-semibold transition-colors cursor-pointer',
    on: 'bg-primary/20 text-foreground',
    off: 'text-muted-foreground hover:text-foreground',
  },
  accent: {
    base: 'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[10px] font-semibold transition-all cursor-pointer',
    on: 'border-primary/40 bg-primary/15 text-primary',
    off: 'border-white/15 dark:border-white/10 bg-accent/30 text-muted-foreground hover:border-primary/40 hover:text-primary',
  },
} as const;

export function HeatmapToggle({
  className,
  showLabel = true,
  variant = 'glass',
}: {
  className?: string;
  showLabel?: boolean;
  variant?: keyof typeof VARIANTS;
}) {
  const active = useInvestorEyeStore((s) => s.activeLayers.includes(HEATMAP_LAYER));
  const toggleLayer = useInvestorEyeStore((s) => s.toggleLayer);
  const v = VARIANTS[variant];

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
      className={cn(v.base, active ? v.on : v.off, className)}
    >
      <Flame size={12} />
      {showLabel && <span>Heatmap</span>}
    </button>
  );
}
