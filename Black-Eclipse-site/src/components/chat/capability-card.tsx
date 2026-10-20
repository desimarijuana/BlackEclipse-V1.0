'use client';

import { useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Sparkles,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import type { TranslationKey } from '@/lib/i18n/types';
import { useCommandStore } from '@/lib/search/store';
import {
  coerceCapabilityBuild,
  type CapabilityBuildStatus,
} from '@/lib/harness/capability-types';

const STATUS_KEY: Record<CapabilityBuildStatus, TranslationKey> = {
  gap: 'capabilityCard.status.gap',
  satisfied: 'capabilityCard.status.satisfied',
  one_off: 'capabilityCard.status.one_off',
  needs_source: 'capabilityCard.status.needs_source',
  refused: 'capabilityCard.status.refused',
  active: 'capabilityCard.status.active',
  tested: 'capabilityCard.status.tested',
  unverified: 'capabilityCard.status.unverified',
  approval_required: 'capabilityCard.status.approval_required',
  handoff_required: 'capabilityCard.status.handoff_required',
  disabled: 'capabilityCard.status.disabled',
  retired: 'capabilityCard.status.retired',
};

const SURFACE_KEY: Record<string, TranslationKey> = {
  analysis_run: 'capabilityCard.surface.analysis_run',
  capability_builder: 'capabilityCard.surface.capability_builder',
  existing_capability: 'capabilityCard.surface.existing_capability',
  scaffold_kit: 'capabilityCard.surface.scaffold_kit',
  skill_create: 'capabilityCard.surface.skill_create',
  ui_start_engineering: 'capabilityCard.surface.ui_start_engineering',
  plugin_or_mcp: 'capabilityCard.surface.plugin_or_mcp',
  external_adapter: 'capabilityCard.surface.external_adapter',
  code_agent_or_rsl: 'capabilityCard.surface.code_agent_or_rsl',
};

const TEST_KEY: Record<string, TranslationKey> = {
  verified: 'capabilityCard.testStatus.verified',
  failed: 'capabilityCard.testStatus.failed',
  unverified: 'capabilityCard.testStatus.unverified',
};

function tone(status: CapabilityBuildStatus): string {
  if (status === 'active' || status === 'tested') return 'text-emerald-300';
  if (status === 'unverified' || status === 'approval_required' || status === 'needs_source') {
    return 'text-amber-300';
  }
  if (status === 'handoff_required') return 'text-sky-300';
  if (status === 'disabled' || status === 'retired' || status === 'refused') return 'text-rose-300';
  return 'text-primary';
}

export function CapabilityCard({
  view,
  compact = false,
  onFollowup,
}: {
  view: unknown;
  compact?: boolean;
  onFollowup?: (prompt: string) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const data = coerceCapabilityBuild(view);
  if (!data) return null;

  const checks = data.verification?.checks ?? [];
  const passed = checks.filter((check) => check.ok).length;
  const failed = data.verification?.failed ?? [];
  const surface = data.surface ? SURFACE_KEY[data.surface] : undefined;
  const testKey = data.testStatus ? TEST_KEY[data.testStatus] : undefined;
  const hasPlan = (data.steps?.length ?? 0) > 0 || (data.missing?.length ?? 0) > 0
    || (data.inputs?.length ?? 0) > 0 || Boolean(data.reason) || checks.length > 0;
  const need = data.need ?? data.capabilityId ?? '';
  const canBuild = data.status === 'gap' || data.status === 'needs_source';
  const canHandoff = data.status === 'handoff_required' && Boolean(data.nextTool);
  const canRebuild = (data.status === 'unverified' || data.status === 'disabled')
    && Boolean(data.capabilityId);
  const showActions = Boolean(onFollowup) && !dismissed && (canBuild || canHandoff || canRebuild);

  return (
    <div className={cn('mt-2 rounded-xl border border-border/30 glass-card-subtle', compact ? 'p-2' : 'p-2.5')}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-1.5 text-left text-[11px] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <Sparkles size={11} className="text-primary" />
        <span className={cn('font-medium', tone(data.status))}>{t(STATUS_KEY[data.status])}</span>
        {data.capabilityId ? (
          <span className="font-mono text-[10px] text-foreground/80">
            {data.capabilityId}
            {data.version ? ` v${data.version}` : ''}
          </span>
        ) : null}
        {data.need ? (
          <span className="min-w-0 flex-1 truncate text-muted-foreground/80">{data.need}</span>
        ) : null}
      </button>

      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[9.5px] text-muted-foreground/80">
        {surface ? <span>{t('capabilityCard.surface')}: {t(surface)}</span> : null}
        {data.nextTool ? (
          <span>
            {t('capabilityCard.nextStep')}: <span className="font-mono">{data.nextTool}</span>
          </span>
        ) : null}
        {data.kind ? <span>{t('capabilityCard.kind')}: {data.kind}</span> : null}
        {data.scope ? <span>{t('capabilityCard.scope')}: {data.scope}</span> : null}
        {data.tests && data.tests.length > 0 ? (
          <span>{t('capabilityCard.tests')}: {data.tests.length}</span>
        ) : null}
        {testKey ? (
          <span className={data.testStatus === 'verified' ? 'text-emerald-300/90' : 'text-amber-300/90'}>
            {t(testKey)}
          </span>
        ) : null}
        {data.verification ? (
          <span className={checks.length > 0 && passed === checks.length ? 'text-emerald-300/90' : 'text-amber-300/90'}>
            {checks.length > 0
              ? t('capabilityCard.checks', { passed, total: checks.length })
              : t('capabilityCard.checksNone')}
          </span>
        ) : null}
      </div>

      {showActions ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {canBuild ? (
            <button
              type="button"
              onClick={() => onFollowup?.(t('capabilityCard.buildPrompt', { need }))}
              className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground"
            >
              {t('capabilityCard.build')}
            </button>
          ) : null}
          {canHandoff ? (
            <button
              type="button"
              onClick={() => onFollowup?.(t('capabilityCard.handoffPrompt', {
                tool: data.nextTool ?? '', need,
              }))}
              className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground"
            >
              {t('capabilityCard.continue')}
            </button>
          ) : null}
          {canRebuild ? (
            <button
              type="button"
              onClick={() => onFollowup?.(t('capabilityCard.rebuildPrompt', {
                id: data.capabilityId ?? '',
              }))}
              className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground"
            >
              {t('capabilityCard.rebuild')}
            </button>
          ) : null}
          {hasPlan ? (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="glass-button rounded-lg px-2.5 py-1 text-[10px] text-foreground"
            >
              {t('capabilityCard.showPlan')}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="rounded-lg px-2.5 py-1 text-[10px] text-muted-foreground transition-colors hover:text-foreground"
          >
            {t('capabilityCard.notNow')}
          </button>
        </div>
      ) : null}

      {open ? (
        <div className="mt-2 space-y-2 text-[10px]">
          {hasPlan ? (
            <>
              {data.steps && data.steps.length > 0 ? (
                <div>
                  <p className="font-semibold text-foreground">{t('capabilityCard.plan')}</p>
                  <ol className="mt-0.5 list-decimal space-y-0.5 pl-4 text-muted-foreground">
                    {data.steps.map((step) => <li key={step}>{step}</li>)}
                  </ol>
                </div>
              ) : null}
              {data.missing && data.missing.length > 0 ? (
                <p className="text-amber-300/90">
                  {t('capabilityCard.missing', { what: data.missing.join(', ') })}
                </p>
              ) : null}
              {data.reason ? (
                <p className="text-muted-foreground">{t('capabilityCard.reason', { reason: data.reason })}</p>
              ) : null}
              {checks.length > 0 ? (
                <div>
                  <p className="font-semibold text-foreground">{t('capabilityCard.tests')}</p>
                  <ul className="mt-0.5 space-y-0.5">
                    {checks.map((check) => (
                      <li key={check.name} className={check.ok ? 'text-emerald-300/90' : 'text-rose-300/90'}>
                        {check.ok ? <Check size={10} className="mr-1 inline" /> : <AlertTriangle size={10} className="mr-1 inline" />}
                        {check.name}{check.detail ? ` — ${check.detail}` : ''}
                      </li>
                    ))}
                  </ul>
                  {failed.length > 0 ? (
                    <p className="mt-1 text-rose-300/90">
                      {t('capabilityCard.failedChecks', { what: failed.map((check) => check.name).join(', ') })}
                    </p>
                  ) : null}
                  {data.verification?.stderr ? (
                    <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded-lg border border-rose-500/20 bg-rose-500/5 p-2 font-mono text-[9px] text-rose-200/90">
                      {data.verification.stderr}
                    </pre>
                  ) : null}
                </div>
              ) : null}
              {(data.inputs?.length ?? 0) > 0 || (data.outputs?.length ?? 0) > 0 ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  {data.inputs && data.inputs.length > 0 ? (
                    <div>
                      <p className="font-semibold text-foreground">{t('capabilityCard.inputs')}</p>
                      <ul className="mt-0.5 text-muted-foreground">
                        {data.inputs.map((input) => (
                          <li key={input.name}>
                            <span className="font-mono">{input.name}</span> ({input.kind})
                            {input.required === false ? ' — optional' : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {data.outputs && data.outputs.length > 0 ? (
                    <div>
                      <p className="font-semibold text-foreground">{t('capabilityCard.outputs')}</p>
                      <ul className="mt-0.5 text-muted-foreground">
                        {data.outputs.map((output) => (
                          <li key={output.name}>
                            <span className="font-mono">{output.name}</span> ({output.kind})
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {testKey ? (
                <p className={data.testStatus === 'verified' ? 'text-emerald-300/90' : 'text-amber-300/90'}>
                  {t(testKey)}
                </p>
              ) : null}
            </>
          ) : (
            <p className="text-muted-foreground">{t('capabilityCard.noPlan')}</p>
          )}

          {data.dir || data.sourceDigest || data.testDigest ? (
            <dl className="space-y-0.5 text-[9px] text-muted-foreground/70">
              {data.dir ? (
                <div><dt className="inline font-semibold">{t('capabilityCard.dir')}: </dt><dd className="inline font-mono break-all">{data.dir}</dd></div>
              ) : null}
              {data.sourceDigest ? (
                <div><dt className="inline font-semibold">{t('capabilityCard.source')}: </dt><dd className="inline font-mono break-all">{data.sourceDigest.slice(0, 16)}…</dd></div>
              ) : null}
              {data.testDigest ? (
                <div><dt className="inline font-semibold">{t('capabilityCard.test')}: </dt><dd className="inline font-mono break-all">{data.testDigest.slice(0, 16)}…</dd></div>
              ) : null}
            </dl>
          ) : null}

          {data.capabilityId ? (
            <button
              type="button"
              onClick={() => useCommandStore.getState().dispatch({
                tab: 'ui-builder', subroute: 'studio.generated',
              })}
              className="glass-button rounded-lg px-3 py-1 text-[10px] text-foreground"
            >
              {t('capabilityCard.open')}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
