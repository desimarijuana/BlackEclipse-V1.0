'use client';

// ── AuroraGlow — the app-wide sentiment glow ─────────────────────────────────
// The single reusable mount for the Aurora WebGL backdrop. It owns the sentiment
// subscription (market indices + news score via DataHub) and the user palette,
// then renders the masked top glow. Used by BOTH the app shell and the Command
// Center's fullscreen overlay — fullscreen portals to <body>, so it needs its
// own Aurora rather than relying on the (covered) shell instance.
//
// This keeps ONE source of truth for the sentiment model: the math lives in
// src/lib/aurora-sentiment.ts, the palette in src/lib/aurora/store.ts, and both
// mounts just consume them.

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';
import Aurora from '@/components/ui/Aurora';
import { useTopic, registerTopic, jsonTopic } from '@/lib/workspace/data-hub';
import { auroraSentiment, marketSentimentFromIndices } from '@/lib/aurora-sentiment';
import { useHydrateAuroraPalette, useAuroraPaletteStore } from '@/lib/aurora/store';

// The market topic the shell already relies on. Registering it here makes the
// glow resolve even on a cold boot straight into a tab that never mounts the
// dashboard chunk.
registerTopic(jsonTopic('market:indices:US', '/api/indices?market=US', { ttl: 120_000, interval: 60_000 }));
// News sentiment (tier-weighted 24h score) — a tiny dedicated topic so the glow
// does not depend on the news screen or the dashboard registry being mounted.
registerTopic(jsonTopic('aurora:news-score', '/api/news?limit=1', { ttl: 120_000, interval: 120_000 }));

interface IndexTopic {
  indices?: Array<{ symbol: string; price: number; changePercent: number }>;
  sectors?: Array<{ name: string; change: number }>;
}

/** Combined market+news sentiment in [-1, +1] from the shared topics. */
export function useAuroraSentiment(): number {
  const indices = useTopic<IndexTopic>('market:indices:US');
  const news = useTopic<{ newsScore?: number }>('aurora:news-score');
  const marketScore = useMemo(
    () => marketSentimentFromIndices(indices.data?.indices, indices.data?.sectors),
    [indices.data],
  );
  const newsScore = typeof news.data?.newsScore === 'number' ? news.data.newsScore : null;
  return useMemo(() => auroraSentiment(marketScore, newsScore).score, [marketScore, newsScore]);
}

/**
 * The masked full-viewport top glow. `className` lets the host position it
 * (the shell and the fullscreen overlay place it the same way but at different
 * stacking contexts).
 */
export function AuroraGlow({ className }: { className?: string }) {
  useHydrateAuroraPalette();
  const palette = useAuroraPaletteStore((s) => s.palette);
  const score = useAuroraSentiment();
  return (
    <div
      data-aurora-glow
      className={cn('absolute top-0 left-0 right-0 h-56 z-0 pointer-events-none overflow-hidden', className)}
      style={{
        maskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
        WebkitMaskImage: 'linear-gradient(to bottom, rgba(0,0,0,1) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
      }}
      aria-hidden
    >
      <Aurora sentiment={score} palette={palette} />
    </div>
  );
}
