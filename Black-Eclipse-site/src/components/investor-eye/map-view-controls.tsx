'use client';

// ── Investor Eye — map view controls ─────────────────────────────────────────
// The single place the map's PRESENTATION is chosen: projection (flat map vs 3D
// globe) and surface skin (plain black terminal vs blue lit planet).
//
// Extracted because the same pair of toggles is needed in two places — the
// hero header and the full-page dock — and two hand-rolled copies is exactly how
// one surface ends up missing a control the other has.
//
// Both are pure view state from the store, so switching either re-renders the
// option in place: no data refetch, no chart rebuild (except the projection
// switch, which legitimately swaps the base component).

import { Layers2, Sparkles, Sun } from 'lucide-react';
import { MAP_SKINS, useInvestorEyeStore, type MapMode } from '@/lib/investor-eye/store';
import { cn } from '@/lib/utils';

const MODES: Array<{ id: MapMode; label: string; hint: string }> = [
  { id: '2d', label: 'MAP', hint: 'Flat map' },
  { id: 'globe', label: 'GLOBE', hint: '3D globe' },
];

interface MapViewControlsProps {
  className?: string;
  /** Hide the text labels, leaving the icons — for tight docks. */
  compact?: boolean;
}

export function MapViewControls({ className, compact = false }: MapViewControlsProps) {
  const mapMode = useInvestorEyeStore((s) => s.mapMode);
  const setMapMode = useInvestorEyeStore((s) => s.setMapMode);
  const mapSkin = useInvestorEyeStore((s) => s.mapSkin);
  const setMapSkin = useInvestorEyeStore((s) => s.setMapSkin);
  const showStars = useInvestorEyeStore((s) => s.showStars);
  const setShowStars = useInvestorEyeStore((s) => s.setShowStars);

  return (
    <div className={cn('glass-button flex items-center gap-0.5 rounded-lg p-0.5', className)}>
      {MODES.map((m) => (
        <button
          key={m.id}
          type="button"
          onClick={() => setMapMode(m.id)}
          title={m.hint}
          aria-pressed={mapMode === m.id}
          className={cn(
            'flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold transition-colors cursor-pointer',
            mapMode === m.id
              ? m.id === '2d' ? 'bg-sky-500/25 text-sky-200' : 'bg-violet-500/25 text-violet-200'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Layers2 size={11} />
          {!compact && m.label}
        </button>
      ))}

      {/* Divider: projection and skin are independent choices. */}
      <span className="mx-0.5 h-4 w-px bg-white/10" aria-hidden="true" />

      {MAP_SKINS.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => setMapSkin(s.id)}
          title={s.hint}
          aria-pressed={mapSkin === s.id}
          className={cn(
            'flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold transition-colors cursor-pointer',
            mapSkin === s.id
              ? s.id === 'black' ? 'bg-white/10 text-foreground' : 'bg-cyan-500/25 text-cyan-100'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Sun size={11} />
          {!compact && s.label}
        </button>
      ))}

      {/* Divider: decoration is independent of the surface and the projection. */}
      <span className="mx-0.5 h-4 w-px bg-white/10" aria-hidden="true" />

      {/* Stars are purely decorative, so they get a plain on/off rather than a
          third skin. The button says what it will DO when clicked. */}
      <button
        type="button"
        onClick={() => setShowStars(!showStars)}
        title={showStars ? 'Hide the starfield' : 'Show the starfield'}
        aria-pressed={showStars}
        className={cn(
          'flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold transition-colors cursor-pointer',
          showStars ? 'bg-indigo-500/25 text-indigo-100' : 'text-muted-foreground hover:text-foreground',
        )}
      >
        <Sparkles size={11} />
        {!compact && (showStars ? 'STARS ON' : 'STARS OFF')}
      </button>
    </div>
  );
}
