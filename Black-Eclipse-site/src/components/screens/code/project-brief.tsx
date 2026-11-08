'use client';

// ── ProjectBriefCard — what Eclipse found before the first build (P5) ────────
// The onboarding answer, in one card: stack, git state, the command that would
// run, the checks a change must pass, and whether the project carries its own
// rules. "Prepare" indexes it so symbol search and repo context are ready.

import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2 } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import {
  getProjectBrief,
  prepareProjectIndex,
  type ProjectBrief,
  type ProjectTarget,
} from '@/lib/harness/code-browser';

const CHECKS_KEY: Record<string, TranslationKey> = {
  detected: 'code.project.checks.detected',
  project: 'code.project.checks.project',
  defaults: 'code.project.checks.defaults',
  none: 'code.project.checks.none',
};

export function ProjectBriefCard({ taskId, rootId }: { taskId?: string | null; rootId?: string | null }) {
  const t = useT();
  const [brief, setBrief] = useState<ProjectBrief | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [prepared, setPrepared] = useState(false);

  const target: ProjectTarget = taskId ? { taskId } : rootId ? { rootId } : {};

  const load = useCallback(async () => {
    try {
      setBrief(await getProjectBrief(target));
    } catch {
      setBrief(null);
    }
  }, [taskId, rootId]);

  useEffect(() => { setPrepared(false); void load(); }, [load]);

  const prepare = async () => {
    setPreparing(true);
    try {
      await prepareProjectIndex();
      setPrepared(true);
    } catch {
      setPrepared(false);
    } finally {
      setPreparing(false);
    }
  };

  if (!brief?.available) return null;
  const checks = brief.checks ?? [];
  const sourceKey = CHECKS_KEY[brief.checksSource ?? 'none'] ?? 'code.project.checks.none';

  return (
    <section className="glass-card-subtle rounded-xl border border-border/40 p-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[12px] font-medium text-foreground">{brief.name}</p>
          <p className="truncate text-[10.5px] text-muted-foreground/60" title={brief.path}>{brief.path}</p>
        </div>
        <button
          type="button"
          onClick={() => void prepare()}
          disabled={preparing}
          className="glass-button inline-flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] text-foreground disabled:opacity-50"
        >
          {preparing ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
          {preparing ? t('code.project.preparing') : prepared ? t('code.project.prepared') : t('code.project.prepare')}
        </button>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-muted-foreground">
        {(brief.stack ?? []).map((name) => (
          <span key={name} className="rounded-full border border-border/40 px-2 py-0.5">{name}</span>
        ))}
        {brief.git?.available ? (
          <span className="rounded-full border border-border/40 px-2 py-0.5">
            {brief.git.branch}
            {brief.git.dirty > 0 ? ` · ${t('code.project.dirty', { count: brief.git.dirty })}` : ''}
          </span>
        ) : null}
        {brief.hasRules ? <span className="text-muted-foreground/70">{t('code.project.rulesOn')}</span> : null}
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
        <span className="min-w-0 truncate">
          {brief.run?.command
            ? t('code.preview.willRun', { command: brief.run.command })
            : t('code.project.noRun')}
        </span>
        <span>
          {t('code.project.checksLabel')}: {checks.length} · {t(sourceKey)}
        </span>
      </div>
    </section>
  );
}
