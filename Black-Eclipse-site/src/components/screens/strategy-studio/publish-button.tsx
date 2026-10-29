'use client';

// ── Publish to the local gallery ────────────────────────────────────────────
// Only a graded strategy can be published, and the grade travels with it. The
// gallery is a local catalogue: it never becomes a market of anonymous signals.

import React, { useState } from 'react';
import type { EdgeReport, StrategyRecord } from '@/lib/backtest/backtest-client';
import { publishStrategy } from '@/lib/strategy-studio/gallery-client';
import { Loader2, Star } from '@/lib/icons';

export function PublishButton({
  strategy,
  report,
  onNotice,
  onError,
}: {
  strategy: StrategyRecord;
  report: EdgeReport;
  onNotice: (message: string) => void;
  onError: (message: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [publishedId, setPublishedId] = useState<string | null>(null);

  if (!report.verdict.available || !report.verdict.grade) return null;

  const publish = async () => {
    setBusy(true);
    onError(null);
    try {
      const spec = strategy.spec as { strategy?: { description?: string }; universe?: { symbols?: string[] } };
      const result = await publishStrategy({
        strategyId: strategy.id,
        version: String(strategy.version ?? strategy.latestVersion),
        name: strategy.name || strategy.id,
        description: spec.strategy?.description ?? '',
        author: 'local',
        grade: report.verdict.grade,
        score: report.verdict.score,
        summary: report.verdict.summary,
        report: report.markdown,
        symbols: spec.universe?.symbols ?? [],
      });
      setPublishedId(result.published?.id ?? 'published');
      onNotice(result.summary);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'could not publish to the gallery');
    } finally {
      setBusy(false);
    }
  };

  if (publishedId) {
    return (
      <span className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 px-2 py-1 font-mono text-[10px] text-emerald-400">
        <Star className="h-3 w-3" /> published {publishedId}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => void publish()}
      disabled={busy}
      className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] disabled:opacity-50"
      title="Publish this graded version into the local gallery"
    >
      {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Star className="h-3 w-3" />}
      Publish to gallery
    </button>
  );
}
