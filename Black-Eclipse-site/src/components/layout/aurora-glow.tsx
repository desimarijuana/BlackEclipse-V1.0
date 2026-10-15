'use client';

// ── AuroraGlow — the app-wide Market Regime glow ────────────────────────────
// The single reusable mount for the Aurora WebGL backdrop. It subscribes to the
// explainable Market Regime reading (not a raw 60/40 blend) and the user
// palette, then renders the masked top glow. Used by BOTH the app shell and the
// Command Center's fullscreen overlay — fullscreen portals to <body>, so it
// needs its own Aurora rather than relying on the (covered) shell instance.
//
// This layer stays DECORATIVE: pointer-events are disabled and the container is
// aria-hidden. The interactive, accessible surface is the top-bar Market Regime
// control (`market-regime-control.tsx`), which reads the same model.
//
// One source of truth for the model: `src/lib/regime/scoring.ts` (the math),
// `src/lib/regime/client.ts` (the subscription), and this file just consumes it.

import React from 'react';
import { cn } from '@/lib/utils';
import Aurora from '@/components/ui/Aurora';
import { useTopic, registerTopic, jsonTopic } from '@/lib/workspace/data-hub';
import { useHydrateAuroraPalette, useAuroraPaletteStore } from '@/lib/aurora/store';
import { useRegime } from '@/lib/regime/client';
import { regimeToAurora } from '@/lib/regime/visuals';

// The market topic the shell already relies on. Registering it here makes the
// glow resolve even on a cold boot straight into a tab that never mounts the
// dashboard chunk.
registerTopic(jsonTopic('market:indices:US', '/api/indices?market=US', { ttl: 120_000, interval: 60_000 }));

/** Combined regime score + dim factor in the shape the Aurora shader wants. */
export function useAuroraSentiment(): { score: number; dim: number } {
  const { result } = useRegime();
  return React.useMemo(() => regimeToAurora(result), [result]);
}

/**
 * The masked full-viewport top glow. `className` lets the host position it
 * (the shell and the fullscreen overlay place it the same way but at different
 * stacking contexts). Always decorative — never a pointer target.
 */
export function AuroraGlow({ className }: { className?: string }) {
  useHydrateAuroraPalette();
  const palette = useAuroraPaletteStore((s) => s.palette);
  const motion = useAuroraPaletteStore((s) => s.motion);
  const shape = useAuroraPaletteStore((s) => s.shape);
  const style = useAuroraPaletteStore((s) => s.style);
  const { score, dim } = useAuroraSentiment();
  return (
    <div
      data-aurora-glow
      className={cn('absolute top-0 left-0 right-0 h-56 z-0 pointer-events-none overflow-hidden', className)}
      style={{
        height: shape.height,
        maskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
        WebkitMaskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
      }}
      aria-hidden
    >
      <Aurora
        sentiment={score}
        dim={dim}
        palette={palette}
        smoothing={motion.response}
        intensityScale={motion.intensity}
        speedScale={motion.speed}
        softnessScale={shape.softness}
        noiseScale={shape.noiseScale}
        style={style.id}
        grid={style.grid}
      />
    </div>
  );
}
