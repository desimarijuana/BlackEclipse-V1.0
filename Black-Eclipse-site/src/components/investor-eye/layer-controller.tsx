'use client';

// ── Investor Eye — Layer Controller ──────────────────────────────────────────
// The single place layer visibility is toggled. It renders from the canonical
// `LAYER_META` registry, so a new layer appears here automatically (spec §24).
//
// Colour-coded: every chip carries its layer's accent (from `LAYER_META`) and is
// grouped by intelligence group, so a dense row still communicates *what is
// what* at a glance. The legend repeats the marker shape so categories are
// distinguishable without relying on colour alone (spec §8 / §34).

import {
  ALL_LAYER_IDS, LAYER_META, SYMBOL_PATHS, groupedLayerIds,
  type LayerId, type LayerSymbol, type SymbolGlyphName,
} from '@/lib/investor-eye/layers';
import { cn } from '@/lib/utils';

interface LayerControllerProps {
  active: LayerId[];
  onToggle: (id: LayerId) => void;
  /** Layers that currently hold data (others render as disabled). */
  available?: Set<string>;
  /** Show the marker-shape legend beneath the chips. */
  showLegend?: boolean;
  className?: string;
}

/** Extract the `d` attribute from a `path://…` glyph definition. */
function pathData(path: string): string {
  return path.replace(/^path:\/\//, '');
}

/**
 * The legend marker for a layer.
 *
 * It renders the layer's ACTUAL glyph — the same `path://` the map draws — so
 * the legend cannot drift from the map. The earlier version switched on a small
 * set of primitive names and silently fell through to a plain dot for every
 * category glyph, which made the legend lie about what each layer looked like.
 */
export function SymbolGlyph({
  glyph,
  symbol,
  color,
  size = 9,
}: {
  glyph?: SymbolGlyphName;
  symbol?: LayerSymbol;
  color: string;
  size?: number;
}) {
  // A category glyph wins, matching `layerSymbol()` in the registry.
  if (glyph) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        aria-hidden="true"
        className="inline-block shrink-0"
        style={{ fill: color }}
      >
        <path d={pathData(SYMBOL_PATHS[glyph])} />
      </svg>
    );
  }
  const s = { width: size, height: size } as React.CSSProperties;
  switch (symbol) {
    case 'diamond':
      return <span style={{ ...s, backgroundColor: color, transform: 'rotate(45deg)' }} className="inline-block rounded-[1px]" />;
    case 'triangle':
      return (
        <span
          style={{
            width: 0, height: 0,
            borderLeft: `${size / 2}px solid transparent`,
            borderRight: `${size / 2}px solid transparent`,
            borderBottom: `${size}px solid ${color}`,
          }}
          className="inline-block"
        />
      );
    case 'square':
      return <span style={{ ...s, backgroundColor: color }} className="inline-block rounded-[1px]" />;
    case 'ring':
      return <span style={{ ...s, borderColor: color }} className="inline-block rounded-full border-2" />;
    default:
      return <span style={{ ...s, backgroundColor: color }} className="inline-block rounded-full" />;
  }
}

export function LayerController({ active, onToggle, available, showLegend = true, className }: LayerControllerProps) {
  const groups = groupedLayerIds();

  return (
    <div className={cn('glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2', className)}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
          Intelligence Layers
        </div>
        <div className="text-[9px] font-mono text-muted-foreground/60">
          {active.length}/{ALL_LAYER_IDS.length} on
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-x-3 gap-y-1.5">
        {groups.map(({ group, ids }) => (
          <div key={group.id} className="flex items-center gap-1">
            {/* Group label — colour-coded rail so the grouping reads instantly. */}
            <span
              className="mr-0.5 select-none rounded-md px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider"
              style={{
                color: group.color,
                backgroundColor: `${group.color}1f`,
                border: `1px solid ${group.color}33`,
              }}
              title={`${group.name} layers`}
            >
              {group.name}
            </span>
            {ids.map((id) => {
              const meta = LAYER_META[id];
              const on = active.includes(id);
              const hasData = available ? available.has(id) : true;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => onToggle(id)}
                  aria-pressed={on}
                  title={
                    hasData
                      ? `${meta.hint} (Phase ${meta.phase})`
                      : `${meta.name} — no data in this window`
                  }
                  className={cn(
                    'group inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[10px] font-semibold transition-all cursor-pointer',
                    on ? 'text-foreground' : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
                    !hasData && 'opacity-45',
                  )}
                  style={
                    on
                      ? { borderColor: `${meta.color}55`, backgroundColor: `${meta.color}26` }
                      : undefined
                  }
                >
                  <SymbolGlyph
                    glyph={meta.glyph}
                    symbol={meta.symbol}
                    color={on ? meta.color : 'currentColor'}
                    size={11}
                  />
                  {meta.name}
                  {meta.phase === 2 && (
                    <span className="rounded-sm border border-border/40 px-1 text-[8px] font-mono text-muted-foreground/70">
                      P2
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {showLegend && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border/10 pt-1.5">
          <span className="text-[8px] font-bold uppercase tracking-widest text-muted-foreground/70">Legend</span>
          {(Object.keys(LAYER_META) as LayerId[]).map((id) => {
            const meta = LAYER_META[id];
            if (!meta.symbol && !meta.glyph) return null;
            return (
              <span key={id} className="inline-flex items-center gap-1 text-[9px] text-muted-foreground">
                <SymbolGlyph glyph={meta.glyph} symbol={meta.symbol} color={meta.color} />
                {meta.name}
              </span>
            );
          })}
          <span className="text-[9px] text-muted-foreground/50">
            marker size = severity
          </span>
          {/* Explain the hollow marker, so an approximate fix is never mistaken
              for an exact position. */}
          <span
            className="inline-flex items-center gap-1 text-[9px] text-muted-foreground/70"
            title="An event known only at country level is plotted at the country centre and drawn as a hollow ring."
          >
            <span className="inline-block h-2 w-2 rounded-full border border-dashed border-muted-foreground/70" />
            country-centre only
          </span>
        </div>
      )}
    </div>
  );
}
