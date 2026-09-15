'use client';

// ── Investor Eye — Layer Controller ──────────────────────────────────────────
// The single place layer visibility is toggled. It renders from the canonical
// `LAYER_META` registry, so a new layer appears here automatically (spec §24).

import { ALL_LAYER_IDS, LAYER_META, type LayerId } from '@/lib/investor-eye/layers';
import { cn } from '@/lib/utils';

interface LayerControllerProps {
  active: LayerId[];
  onToggle: (id: LayerId) => void;
  /** Layers that currently hold data (others render as disabled). */
  available?: Set<string>;
}

export function LayerController({ active, onToggle, available }: LayerControllerProps) {
  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2">
      <div className="mb-1.5 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
        Map Layers
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {ALL_LAYER_IDS.map((id) => {
          const meta = LAYER_META[id];
          const on = active.includes(id);
          const hasData = available ? available.has(id) : true;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onToggle(id)}
              title={
                hasData
                  ? `${meta.name} (Phase ${meta.phase})`
                  : `${meta.name} — no data in this window`
              }
              className={cn(
                'group inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[10px] font-semibold transition-all cursor-pointer border',
                on
                  ? 'border-primary/30 bg-primary/15 text-foreground'
                  : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
                !hasData && 'opacity-45',
              )}
            >
              <span
                className={cn(
                  'inline-block h-2.5 w-2.5 rounded-[3px] border',
                  on ? 'border-primary bg-primary' : 'border-border/60 bg-transparent',
                )}
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
    </div>
  );
}
