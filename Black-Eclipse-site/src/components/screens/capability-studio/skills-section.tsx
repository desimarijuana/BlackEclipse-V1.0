'use client';

// ── Capability Studio · Skills section ──────────────────────────────────────
// A READ-ONLY summary of the skill library inside the studio; every create /
// edit / enable action stays in the Skills manager (evaluation + promotion
// gated), which this section navigates to. Counts and rows come from the real
// registry (`listSkills`); a load failure is shown as a failure — never as an
// empty library.

import { useCallback, useEffect, useState } from 'react';
import { Blocks, RefreshCw } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import { listSkills, type SkillListResult } from '@/lib/harness/clients/skills-browser';

export interface SkillSummaryCounts {
  total: number;
  enabled: number;
  pending: number;
  issues: number;
}

// The statuses that mean "live" in the registry's own vocabulary.
const LIVE_STATUS: ReadonlySet<string> = new Set(['enabled', 'active']);
// An evaluation that has not concluded either way — the skill is not cleared.
const PENDING_EVAL: ReadonlySet<string> = new Set(['not_evaluated', 'needs_review', 'blocked']);
// Conclusions that demand the operator's attention.
const FAILED_STATUS: ReadonlySet<string> = new Set(['rejected', 'rolled_back']);

export function summarizeSkills(result: SkillListResult): SkillSummaryCounts {
  const counts: SkillSummaryCounts = { total: result.skills.length, enabled: 0, pending: 0, issues: 0 };
  for (const skill of result.skills) {
    if (LIVE_STATUS.has(skill.status)) counts.enabled += 1;
    if (PENDING_EVAL.has(skill.evaluationStatus) || skill.status === 'evaluating' || skill.status === 'testing') {
      counts.pending += 1;
    }
    if (FAILED_STATUS.has(skill.status) || skill.evaluationStatus === 'failed') counts.issues += 1;
  }
  // Load errors, quarantines and duplicates are the registry telling us
  // something is wrong — they count as attention, not as an empty list.
  counts.issues += result.loadErrors.length + result.quarantined.length + result.duplicates.length;
  return counts;
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: 'issues' | 'pending' }) {
  return (
    <div className="glass-card-subtle rounded-xl border border-border/20 px-3 py-2.5">
      <div
        className={cn(
          'font-mono text-lg tabular-nums',
          tone === 'issues' && value > 0 ? 'text-amber-300' : tone === 'pending' && value > 0 ? 'text-sky-300' : 'text-foreground',
        )}
      >
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  );
}

export function SkillsSection({ onOpenSkills }: { onOpenSkills: () => void }) {
  const t = useT();
  const [result, setResult] = useState<SkillListResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setResult(await listSkills());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-xs text-muted-foreground">{t('studio.loading')}</p>;
  }
  if (error || !result) {
    return (
      <div className="glass-card-subtle rounded-xl border border-rose-500/20 px-3 py-2.5 text-xs text-rose-200">
        <p>{t('studio.loadFailed', { what: t('studio.section.skills').toLowerCase(), reason: error ?? 'unavailable' })}</p>
        <button type="button" onClick={() => void load()} className="glass-button mt-2 rounded-lg px-3 py-1 text-[11px] text-foreground">
          {t('studio.retry')}
        </button>
      </div>
    );
  }

  const counts = summarizeSkills(result);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <StatCard label={t('studio.skills.total')} value={counts.total} />
        <StatCard label={t('studio.skills.enabled')} value={counts.enabled} />
        <StatCard label={t('studio.skills.pending')} value={counts.pending} tone="pending" />
        <StatCard label={t('studio.skills.issues')} value={counts.issues} tone="issues" />
      </div>

      <div className="glass-card rounded-xl p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            <Blocks size={12} /> {t('studio.section.skills')}
          </h2>
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={() => void load()} aria-label={t('studio.retry')} className="rounded-md p-1 text-muted-foreground hover:text-foreground">
              <RefreshCw size={12} />
            </button>
            <button type="button" onClick={onOpenSkills} className="glass-button rounded-lg px-3 py-1 text-[11px] text-foreground">
              {t('studio.open', { what: t('nav.skills') })}
            </button>
          </div>
        </div>
        {result.skills.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('studio.skills.empty')}</p>
        ) : (
          <ul className="divide-y divide-border/15">
            {result.skills.slice(0, 8).map((skill) => (
              <li key={`${skill.id}@${skill.version}`} className="flex items-center justify-between gap-2 py-1.5 text-xs">
                <span className="min-w-0 flex-1 truncate text-foreground">{skill.name}</span>
                <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{skill.status}</span>
                <span
                  className={cn(
                    'shrink-0 rounded-full border px-1.5 py-px font-mono text-[9px] uppercase tracking-wide',
                    skill.evaluationStatus === 'passed'
                      ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
                      : skill.evaluationStatus === 'failed'
                        ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                        : 'border-amber-500/25 bg-amber-500/10 text-amber-300',
                  )}
                >
                  {skill.evaluationStatus}
                </span>
              </li>
            ))}
          </ul>
        )}
        {result.skills.length > 8 ? (
          <p className="mt-1 text-[10px] text-muted-foreground">+{result.skills.length - 8}</p>
        ) : null}
      </div>
    </div>
  );
}
