'use client';

// ── Self-build scorecard strip (Phase 22 / S6) ──────────────────────────────
// Four counts, each with its own denominator. A dimension the runtime cannot
// measure is not shown as zero - only measured counts appear here.

import { useT } from '@/lib/i18n/use-t';
import type { CodeScorecard } from '@/lib/harness/code-browser';

export function ScorecardStrip({ card }: { card: CodeScorecard | null }) {
  const t = useT();
  if (!card) return null;
  const m = card.metrics;
  return (
    <div className="glass-card-subtle flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-xl border border-border/40 px-3 py-1.5 text-[11px] text-muted-foreground">
      <span className="text-foreground">{t('code.scorecard.title')}</span>
      <span aria-hidden>·</span>
      <span>{t('code.scorecard.builds')} {m.builds}</span>
      <span aria-hidden>·</span>
      <span>{t('code.scorecard.landed')} {m.landed}</span>
      <span aria-hidden>·</span>
      <span>{t('code.scorecard.firstPass')} {m.firstPassChecks}/{m.checked}</span>
      <span aria-hidden>·</span>
      <span>{t('code.scorecard.rollbacks')} {m.rolledBack}</span>
    </div>
  );
}
