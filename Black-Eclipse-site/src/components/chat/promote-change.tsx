'use client';

// ── Promote a made change (Phase 15) ─────────────────────────────────────────
// A chat or code turn edits a disposable copy. This control lets the USER put the
// change into their real project: it previews exactly which files would change,
// then applies them only after an explicit confirmation. The runtime records a
// single-use decision bound to the previewed set; this component never decides.
//
// Every string is an i18n key under `code.promote.*` and the mechanism words
// (patch/diff/repo/commit/branch) never appear.

import { useState } from 'react';
import { Check, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import { previewPromotion, applyPromotion, rollbackPromotion, restartHarnessRuntime } from '@/lib/harness/code-browser';
import type { PromotionPreview, PromotionLanding } from '@/lib/harness/code-browser';

type Phase = 'idle' | 'loading' | 'preview' | 'applying' | 'done' | 'rolling_back' | 'rolled_back' | 'error';

const MAX_SHOWN_FILES = 12;

function opKey(op: PromotionPreview['files'][number]['op']): TranslationKey {
  if (op === 'create') return 'code.promote.fileNew';
  if (op === 'delete') return 'code.promote.fileRemoved';
  return 'code.promote.fileEdited';
}

function errorKey(message: string): TranslationKey {
  const code = message.toUpperCase();
  if (code.includes('BASE_CHANGED')) return 'code.promote.error.base';
  if (code.includes('PREVIEW_STALE')) return 'code.promote.error.stale';
  if (code.includes('OUT_OF_SCOPE')) return 'code.promote.error.scope';
  if (code.includes('NO_CHANGE')) return 'code.promote.empty';
  return 'code.promote.error.generic';
}

export interface PromoteChangeProps {
  /** The run whose prepared change is offered. */
  runId: string;
  compact?: boolean;
}

export function PromoteChange({ runId, compact = false }: PromoteChangeProps) {
  const t = useT();
  const [phase, setPhase] = useState<Phase>('idle');
  const [preview, setPreview] = useState<PromotionPreview | null>(null);
  const [approvalId, setApprovalId] = useState<string | null>(null);
  const [rollbackId, setRollbackId] = useState<string | null>(null);
  const [landing, setLanding] = useState<PromotionLanding | null>(null);
  const [restart, setRestart] = useState<'idle' | 'working' | 'done' | 'error'>('idle');
  const [messageKey, setMessageKey] = useState<TranslationKey>('code.promote.error.generic');

  async function review() {
    setPhase('loading');
    try {
      const { preview: result, approval, landing: verdict } = await previewPromotion(runId);
      if (!result || result.filesChanged === 0 || !approval?.id) {
        setMessageKey('code.promote.empty');
        setPhase('error');
        return;
      }
      setPreview(result);
      setApprovalId(approval.id);
      setLanding(verdict ?? null);
      setPhase('preview');
    } catch (err) {
      setMessageKey(errorKey(err instanceof Error ? err.message : ''));
      setPhase('error');
    }
  }

  async function confirm() {
    if (!preview || !approvalId) return;
    setPhase('applying');
    try {
      const result = await applyPromotion(runId, approvalId, preview.previewDigest);
      setRollbackId(result.rollbackId ?? null);
      if (result.landing) setLanding(result.landing);
      setPhase('done');
    } catch (err) {
      setMessageKey(errorKey(err instanceof Error ? err.message : ''));
      setPhase('error');
    }
  }

  async function rollback() {
    if (!rollbackId) return;
    setPhase('rolling_back');
    try {
      await rollbackPromotion(rollbackId);
      setPhase('rolled_back');
    } catch (err) {
      setMessageKey(errorKey(err instanceof Error ? err.message : ''));
      setPhase('error');
    }
  }

  async function doRestart() {
    setRestart('working');
    try {
      const ok = await restartHarnessRuntime();
      setRestart(ok ? 'done' : 'error');
    } catch {
      setRestart('error');
    }
  }

  function reset() {
    setPhase('idle');
    setPreview(null);
    setApprovalId(null);
    setRollbackId(null);
    setLanding(null);
  }

  const size = compact ? 'text-[10.5px]' : 'text-[11.5px]';

  if (phase === 'idle') {
    return (
      <button
        type="button"
        onClick={() => void review()}
        className={cn(
          'glass-card-subtle mt-2 rounded-lg border border-border/40 px-3 py-1 text-foreground hover:bg-accent',
          size,
        )}
      >
        {t('code.promote.review')}
      </button>
    );
  }

  if (phase === 'loading' || phase === 'applying' || phase === 'rolling_back') {
    const key: TranslationKey =
      phase === 'loading' ? 'code.promote.reviewing'
      : phase === 'rolling_back' ? 'code.promote.rollingBack'
      : 'code.promote.working';
    return (
      <div className={cn('mt-2 text-muted-foreground', size)}>
        {t(key)}
      </div>
    );
  }

  if (phase === 'rolled_back') {
    return (
      <div className={cn('glass-card-subtle mt-2 flex items-center gap-2 rounded-lg border border-border/40 px-3 py-1.5 text-foreground', size)}>
        <Check size={compact ? 11 : 12} className="shrink-0 text-primary" />
        <span>{t('code.promote.rolledBack')}</span>
      </div>
    );
  }

  if (phase === 'done') {
    return (
      <div className={cn('glass-card-subtle mt-2 rounded-lg border border-border/40 px-3 py-1.5 text-foreground', size)}>
        <div className="flex items-center gap-2">
          <Check size={compact ? 11 : 12} className="shrink-0 text-primary" />
          <span>{t('code.promote.done')}</span>
        </div>
        {landing?.restartRequired && (
          <div className="mt-1 text-muted-foreground/80">
            {t('code.promote.restartNote')}
            {restart === 'idle' && (
              <button
                type="button"
                onClick={() => void doRestart()}
                className="ml-2 rounded-lg border border-border/40 px-2.5 py-0.5 text-foreground hover:bg-accent"
              >
                {t('code.promote.restartNow')}
              </button>
            )}
            {restart === 'working' && <span className="ml-2">{t('code.promote.restarting')}</span>}
            {restart === 'done' && <span className="ml-2 text-primary">{t('code.promote.restarted')}</span>}
            {restart === 'error' && <span className="ml-2 text-destructive">{t('code.promote.restartFailed')}</span>}
          </div>
        )}
        {landing?.buildRequired && (
          <div className="mt-1 text-muted-foreground/80">{t('code.promote.buildNote')}</div>
        )}
        {rollbackId && (
          <button
            type="button"
            onClick={() => void rollback()}
            className="mt-1.5 rounded-lg border border-border/40 px-2.5 py-0.5 text-muted-foreground hover:bg-accent"
          >
            {t('code.promote.rollback')}
          </button>
        )}
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className={cn('glass-card-subtle mt-2 flex items-center gap-2 rounded-lg border border-border/40 px-3 py-1.5 text-muted-foreground', size)}>
        <X size={compact ? 11 : 12} className="shrink-0 text-destructive" />
        <span className="min-w-0 flex-1">{t(messageKey)}</span>
        <button type="button" onClick={reset} className="shrink-0 underline-offset-2 hover:underline">
          {t('code.promote.review')}
        </button>
      </div>
    );
  }

  // preview
  const files = preview?.files ?? [];
  const shown = files.slice(0, MAX_SHOWN_FILES);
  const extra = files.length - shown.length;
  return (
    <div className={cn('glass-card mt-2 rounded-xl border border-border/40 p-2.5', size)}>
      <div className="text-foreground">{t('code.promote.title')}</div>
      <ul className="mt-1 space-y-0.5 font-mono text-muted-foreground/80">
        {shown.map((f) => (
          <li key={`${f.op}:${f.path}`} className="truncate">
            {t(opKey(f.op), { name: f.path })}
          </li>
        ))}
        {extra > 0 && <li className="text-muted-foreground/60">{t('code.promote.more', { count: extra })}</li>}
      </ul>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void confirm()}
          className="rounded-lg bg-primary/90 px-3 py-1 text-primary-foreground hover:bg-primary"
        >
          {t('code.promote.confirm')}
        </button>
        <button
          type="button"
          onClick={reset}
          className="rounded-lg border border-border/40 px-3 py-1 text-muted-foreground hover:bg-accent"
        >
          {t('code.promote.cancel')}
        </button>
      </div>
    </div>
  );
}
