'use client';

// ── "Proof it works" — the Phase 4 code-verification panel ──────────────────
// A compact, frosted-glass view of what the executor actually recorded for a
// run. It renders BELOW the assistant answer, beside research-evidence-panel.tsx.
//
// It NEVER prints "verified" for a claim the runtime marked unsupported — the
// status word comes straight from the blob. The internal `UNVERIFIED` marker in
// the persisted answer is rendered as plain language ("not checked yet"); the
// mechanism (check name, exit code, output digest) lives behind a details
// affordance. Every user-facing string is an i18n key — never hardcoded — so the
// jargon gate can scan it.

import { useState } from 'react';
import { ChevronDown, ChevronRight, ShieldAlert, ShieldCheck } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import { claimStatusKey, coerceCodeVerification } from '@/lib/harness/code-browser';

export interface CodeVerificationPanelProps {
  verification: unknown;
  compact?: boolean;
}

/** Short monospace form of a digest for the details affordance. */
function shortDigest(digest: string | null | undefined): string {
  if (!digest) return '—';
  return digest.slice(0, 12);
}

export function CodeVerificationPanel({ verification, compact = false }: CodeVerificationPanelProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const data = coerceCodeVerification(verification);
  if (!data) return null;

  const passedRecords = data.records.filter((r) => r.exitCode === 0);
  const failedRecords = data.records.filter((r) => r.exitCode !== 0);
  const unbacked = data.claims.filter((c) => !c.supported);

  return (
    <div className={cn('glass-card-subtle rounded-xl border border-border/40 p-3', compact ? 'text-[11px]' : 'text-[12px]')}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-left"
      >
        {failedRecords.length > 0 || unbacked.length > 0
          ? <ShieldAlert size={13} className="shrink-0 text-amber-500" />
          : <ShieldCheck size={13} className="shrink-0 text-emerald-500" />}
        <span className="min-w-0 flex-1 font-medium text-foreground">{t('code.proof.title')}</span>
        <span className="shrink-0 text-muted-foreground/70">
          {t('code.proof.checks', { count: data.records.length })}
        </span>
        <ChevronRight size={12} className={cn('shrink-0 text-muted-foreground/40 transition-transform', open && 'rotate-90')} />
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {/* Checks — one plain line per execution. */}
          <ul className="space-y-0.5">
            {data.records.map((r) => (
              <li key={r.commandExecutionId} className="flex items-center gap-2">
                <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', r.exitCode === 0 ? 'bg-emerald-500' : 'bg-rose-500')} />
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {r.exitCode === 0
                    ? t('code.proof.checkPassed', { seconds: (r.durationMs / 1000).toFixed(1) })
                    : t('code.proof.checkFailed')}
                </span>
                <span className="shrink-0 font-mono text-[10px] text-muted-foreground/50">
                  {t('code.proof.details')}: {r.commandClass} · {r.exitCode} · {shortDigest(r.outputDigest)}
                </span>
              </li>
            ))}
            {passedRecords.length === 0 && failedRecords.length === 0 && (
              <li className="text-muted-foreground/70">{t('code.proof.noChecks')}</li>
            )}
          </ul>

          {/* Claims — an unsupported claim is NEVER labelled verified. */}
          {data.claims.length > 0 && (
            <ul className="space-y-0.5 border-t border-border/30 pt-1.5">
              {data.claims.map((c, i) => (
                <li key={`${c.kind}-${i}`} className="flex items-start gap-2">
                  <span className={cn('mt-1 h-1.5 w-1.5 shrink-0 rounded-full', c.supported ? 'bg-emerald-500' : 'bg-amber-500')} />
                  <span className="min-w-0 flex-1 text-muted-foreground">{c.sentence}</span>
                  <span className={cn('shrink-0', c.supported ? 'text-emerald-500' : 'text-amber-500')}>
                    {t(claimStatusKey(c.supported))}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {/* Repair — only when one ran. */}
          {data.repair && (
            <div className="border-t border-border/30 pt-1.5 text-muted-foreground/70">
              {data.repair.status === 'passed'
                ? t('code.proof.repairPassed', { attempts: data.repair.repairAttempts })
                : t('code.proof.repairFailed', { attempts: data.repair.repairAttempts, max: data.repair.maxAttempts })}
            </div>
          )}

          {data.truncated && (
            <div className="text-muted-foreground/60">{t('code.proof.truncated')}</div>
          )}
        </div>
      )}
    </div>
  );
}
