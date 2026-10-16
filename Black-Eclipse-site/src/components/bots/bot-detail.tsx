'use client';

// Bot detail: a polished inspection surface, not a raw config dump. Organizes
// Overview / Instructions / Schedule / Capabilities / Memory / Run history /
// Settings. Every value comes from the persisted automation; edits call the real
// API and never claim success before it is confirmed.

import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import {
  AlertTriangle, ArrowLeft, CalendarDays, CheckCircle2, ChevronDown, Eye, ListChecks,
  MoreHorizontal, Pause, Play, Settings, ShieldCheck, Sparkles, SquarePen, Trash2,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { GhostCustomizer } from '@/components/bots/ghost-customizer';
import { ScheduleEditor } from '@/components/bots/schedule-editor';
import { RunBehaviourEditor } from '@/components/bots/run-behaviour-editor';
import { BotModelPicker } from '@/components/bots/bot-model-picker';
import { BreakerPill, ExecutionPill, LifecyclePill } from '@/components/bots/status-pill';
import { RunHistory } from '@/components/bots/run-history';
import { BotMemorySection } from '@/components/bots/bot-memory-section';
import {
  disableAutomation,
  enableAutomation,
  getAutomationStatus,
  pauseAutomation,
  resumeAutomation,
  updateAutomation,
  type AutomationStatusView,
  type AutomationView,
} from '@/lib/harness/automation-browser';
import { avatarFor, useBotAvatarStore } from '@/lib/bots/avatar-store';
import {
  buildModelConfig, buildPolicies, buildTrigger, draftFromBot, formatDateTime, formatRelative,
  isTerminalExecution, scheduleSummary, triggerKindLabel, validateDraft, type BotDraft,
} from '@/lib/bots/state';

export interface BotDetailProps {
  bot: AutomationView;
  busy: boolean;
  /** Bumped by the parent when a run is triggered, to refresh history. */
  refreshKey?: number;
  onClose: () => void;
  onChanged: () => void;
  onRunNow: (bot: AutomationView) => void;
  onDuplicate: (bot: AutomationView) => void;
  onDelete: (bot: AutomationView) => void;
}

export function BotDetail({ bot, busy, refreshKey = 0, onClose, onChanged, onRunNow, onDuplicate, onDelete }: BotDetailProps) {
  const t = useT();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const setAvatar = useBotAvatarStore((s) => s.setAvatar);
  const randomize = useBotAvatarStore((s) => s.randomize);
  const resetAvatar = useBotAvatarStore((s) => s.resetAvatar);

  const [status, setStatus] = useState<AutomationStatusView | null>(null);
  const [editingAvatar, setEditingAvatar] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await getAutomationStatus(bot.id));
    } catch {
      /* status is best-effort */
    }
  }, [bot.id]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus, bot.version]);

  // Poll status only while the latest run is live.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const last = status?.lastExecution;
    if (last && !isTerminalExecution(last.state)) {
      timer.current = setTimeout(() => void loadStatus(), 4000);
    }
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [status, loadStatus]);

  const runAction = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusyAction(true);
      setError(null);
      try {
        await fn();
        await loadStatus();
        onChanged();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'action failed');
      } finally {
        setBusyAction(false);
      }
    },
    [loadStatus, onChanged],
  );

  const spec = avatarFor(avatars, bot.id);
  const last = status?.lastExecution ?? null;

  return (
    <div className="glass-card flex h-full min-h-0 flex-col rounded-2xl">
      {/* Header */}
      <div className="flex items-start gap-3 border-b border-border/10 p-4">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/10 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
          aria-label={t('common.close')}
        >
          <ArrowLeft size={16} />
        </button>
        <button
          type="button"
          onClick={() => setEditingAvatar((v) => !v)}
          title={t('bots.customize')}
          className="rounded-2xl transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <GhostAvatar spec={spec} size={56} title={bot.name} />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-base font-semibold">{bot.name}</h2>
            <LifecyclePill state={bot.state} />
            {last && <ExecutionPill state={last.state} />}
            <BreakerPill state={bot.breaker} />
          </div>
          {bot.description && (
            <p className="mt-0.5 line-clamp-2 break-words text-xs text-muted-foreground">{bot.description}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Button size="sm" disabled={busy || busyAction || bot.state !== 'active'} onClick={() => onRunNow(bot)}>
              <Play size={13} /> {t('bots.runNow')}
            </Button>
            {bot.state === 'active' && (
              <Button size="sm" variant="outline" disabled={busyAction} onClick={() => runAction(() => pauseAutomation(bot.id))}>
                <Pause size={13} /> {t('bots.pause')}
              </Button>
            )}
            {bot.state === 'paused' && (
              <Button size="sm" variant="outline" disabled={busyAction} onClick={() => runAction(() => resumeAutomation(bot.id))}>
                <Play size={13} /> {t('bots.resume')}
              </Button>
            )}
            {(bot.state === 'draft' || bot.state === 'validating' || bot.state === 'disabled') && (
              <Button size="sm" variant="outline" disabled={busyAction} onClick={() => runAction(() => enableAutomation(bot.id))}>
                {t('bots.enable')}
              </Button>
            )}

            {/* Secondary/destructive actions live behind a menu so the header
                keeps one clear primary path (Run now) instead of seven buttons. */}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={<Button size="icon-sm" variant="ghost" aria-label={t('bots.more')} title={t('bots.more')} />}
              >
                <MoreHorizontal size={16} />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                {bot.state === 'active' && (
                  <DropdownMenuItem onClick={() => runAction(() => disableAutomation(bot.id))}>
                    {t('bots.disable')}
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={() => onDuplicate(bot)}>
                  {t('bots.duplicate')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onClick={() => onDelete(bot)}>
                  <Trash2 size={14} /> {t('bots.delete')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <button
              type="button"
              onClick={() => onClose()}
              className="ml-auto hidden rounded-lg p-1.5 text-muted-foreground hover:bg-white/10 hover:text-foreground lg:block"
              aria-label={t('common.close')}
            >
              <ArrowLeft size={16} />
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="mx-4 mt-3 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
          {error}
        </div>
      )}

      {editingAvatar && (
        <div className="p-4">
          <GhostCustomizer
            spec={spec}
            onChange={(next) => setAvatar(bot.id, next)}
            onRandomize={() => randomize(bot.id)}
            onReset={() => resetAvatar(bot.id)}
          />
        </div>
      )}

      {/* Sections — collapsible dropdowns in one scrollable column. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
        <div className="divide-y divide-border/10">
          <SectionBlock icon={Eye} title={t('bots.detail.overview')} defaultOpen>
            <OverviewSection bot={bot} status={status} />
          </SectionBlock>

          <SectionBlock icon={SquarePen} title={t('bots.detail.instructions')}>
            <InstructionsSection bot={bot} onChanged={onChanged} />
          </SectionBlock>

          <SectionBlock icon={CalendarDays} title={t('bots.detail.schedule')}>
            <ScheduleSection bot={bot} onChanged={onChanged} />
          </SectionBlock>

          <SectionBlock icon={ShieldCheck} title={t('bots.detail.capabilities')}>
            <CapabilitiesSection bot={bot} />
          </SectionBlock>

          <SectionBlock icon={Sparkles} title={t('bots.detail.memory')}>
            <BotMemorySection botId={bot.id} />
          </SectionBlock>

          <SectionBlock icon={ListChecks} title={t('bots.detail.history')}>
            <RunHistory botId={bot.id} refreshKey={refreshKey} />
          </SectionBlock>

          <SectionBlock icon={Settings} title={t('bots.detail.settings')}>
            <SettingsSection bot={bot} />
          </SectionBlock>
        </div>
      </div>
    </div>
  );
}

function SectionBlock({
  icon: Icon, title, defaultOpen = false, children,
}: {
  icon: typeof Eye;
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group flex w-full cursor-pointer items-center gap-2 py-3 text-left"
      >
        <Icon size={14} className="shrink-0 text-primary/70" />
        <span className="flex-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground transition-colors group-hover:text-foreground">
          {title}
        </span>
        <ChevronDown
          size={14}
          className={cn('shrink-0 text-muted-foreground transition-transform', !open && '-rotate-90')}
        />
      </button>
      {open && <div className="pb-4">{children}</div>}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm text-foreground">{children}</dd>
    </div>
  );
}

function OverviewSection({ bot, status }: { bot: AutomationView; status: AutomationStatusView | null }) {
  const t = useT();
  const last = status?.lastExecution ?? null;
  const warnings: string[] = [];
  if (bot.breaker === 'open') warnings.push(t('bots.filter.attention'));
  if (bot.consecutiveFailures > 0) warnings.push(`${bot.consecutiveFailures} consecutive failures`);
  return (
    <div className="space-y-3">
      {warnings.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{warnings.join(' · ')}</span>
        </div>
      )}

      <section className="glass-card-subtle rounded-xl p-4">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('bots.detail.identity')}
        </h3>
        {/* The purpose is often a multi-line brief — give it the full width and
            preserve its line breaks instead of collapsing it into one blob in a
            narrow grid cell. */}
        <div className="mt-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t('bots.purpose')}</div>
          <div className="mt-1 whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground">
            {bot.description || bot.action.objective || '—'}
          </div>
        </div>
        <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t('bots.create.agent')}>{bot.action.agentId ?? 'eclipse-agent'}</Field>
          <Field label={t('bots.scope')}>{bot.scopeId ?? 'Personal'}</Field>
          <Field label={t('bots.status')}>{bot.state}</Field>
        </dl>
      </section>

      <section className="glass-card-subtle rounded-xl p-4">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('bots.detail.activity')}
        </h3>
        <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t('bots.triggerLabel')}>{triggerKindLabel(bot.trigger.type)}</Field>
          <Field label={t('bots.detail.schedule')}>{scheduleSummary(bot.trigger)}</Field>
          <Field label={t('bots.nextRun')}>{bot.nextRunAt ? `${formatRelative(bot.nextRunAt)} · ${formatDateTime(bot.nextRunAt)}` : t('bots.never')}</Field>
          <Field label={t('bots.lastRun')}>{bot.lastRunAt ? `${formatRelative(bot.lastRunAt)} · ${formatDateTime(bot.lastRunAt)}` : t('bots.never')}</Field>
          <Field label={t('bots.lastOutcome')}>{last ? last.state.replace('_', ' ') : t('bots.noRunsYet')}</Field>
          {status && (
            <Field label={t('bots.successRate')}>
              {status.successRate == null ? '—' : `${Math.round(status.successRate * 100)}% (${status.successCount}/${status.executionCount})`}
            </Field>
          )}
        </dl>
      </section>
    </div>
  );
}

function InstructionsSection({ bot, onChanged }: { bot: AutomationView; onChanged: () => void }) {
  const t = useT();
  const saved = bot.action.objective ?? '';
  const [text, setText] = useState(saved);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const dirty = text.trim() !== saved.trim();

  useEffect(() => {
    setText(saved);
  }, [saved]);

  const save = async () => {
    if (saving || !text.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await updateAutomation(bot.id, {
        action: { ...bot.action, objective: text.trim() },
        description: bot.description ?? text.trim(),
      });
      setFlash(true);
      setTimeout(() => setFlash(false), 2000);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        className="min-h-40 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        aria-label={t('bots.detail.instructions')}
      />
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={save} disabled={saving || !dirty}>
          {saving ? t('bots.saving') : t('bots.save')}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setText(saved)} disabled={!dirty}>
          {t('bots.cancelEdit')}
        </Button>
        {dirty && <span className="text-xs text-amber-300">{t('bots.unsavedChanges')}</span>}
        {flash && !dirty && (
          <span className="inline-flex items-center gap-1 text-xs text-emerald-300">
            <CheckCircle2 size={13} weight="fill" /> {t('bots.instructionsSaved')}
          </span>
        )}
      </div>
      {error && <p className="text-xs text-rose-300">{error}</p>}
    </div>
  );
}

function ScheduleSection({ bot, onChanged }: { bot: AutomationView; onChanged: () => void }) {
  const t = useT();
  const [draft, setDraft] = useState<BotDraft>(() => draftFromBot(bot));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    setDraft(draftFromBot(bot));
  }, [bot]);

  const save = async () => {
    const issues = validateDraft(draft);
    if (issues.length) {
      setError(issues[0].message);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const nextConfig: Record<string, unknown> = { ...(bot.action.config ?? {}), ...buildModelConfig(draft) };
      if (!draft.model) delete nextConfig.modelSettings;
      const updated = await updateAutomation(bot.id, {
        trigger: buildTrigger(draft),
        ...buildPolicies(draft),
        action: { ...bot.action, config: nextConfig },
      });
      setFlash(updated.nextRunAt ? t('bots.scheduleUpdated', { next: formatDateTime(updated.nextRunAt) }) : t('bots.instructionsSaved'));
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <ScheduleEditor draft={draft} onChange={(p) => setDraft((d) => ({ ...d, ...p }))} />
      <BotModelPicker
        provider={draft.modelProvider}
        model={draft.model}
        onChange={(p) => setDraft((d) => ({ ...d, ...p }))}
      />
      <div>
        <div className="mb-1 text-[11px] font-medium text-muted-foreground">{t('bots.behaviour.title')}</div>
        <RunBehaviourEditor draft={draft} onChange={(p) => setDraft((d) => ({ ...d, ...p }))} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{t('bots.nextRun')}: <span className="text-foreground">{bot.nextRunAt ? formatDateTime(bot.nextRunAt) : t('bots.never')}</span></span>
        <span>{t('bots.lastRun')}: <span className="text-foreground">{bot.lastRunAt ? formatDateTime(bot.lastRunAt) : t('bots.never')}</span></span>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={save} disabled={saving}>
          {saving ? t('bots.saving') : t('bots.save')}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setDraft(draftFromBot(bot))} disabled={saving}>
          {t('bots.cancelEdit')}
        </Button>
        {flash && <span className="text-xs text-emerald-300">{flash}</span>}
      </div>
      {error && <p className="text-xs text-rose-300">{error}</p>}
    </div>
  );
}

function CapabilitiesSection({ bot }: { bot: AutomationView }) {
  const t = useT();
  const perms = bot.permissions;
  const hasDetail = perms.allowed.length > 0 || perms.denied.length > 0 || bot.tags.length > 0;
  return (
    <div className="space-y-3 text-sm">
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t('bots.create.agent')}>{bot.action.agentId ?? 'eclipse-agent'}</Field>
        <Field label={t('bots.scope')}>{bot.scopeId ?? 'Personal'}</Field>
        <Field label={t('bots.requiresApproval')}>
          {perms.requiresApproval ? (perms.approvalScope ?? 'Yes') : t('bots.noApproval')}
        </Field>
      </dl>
      {hasDetail ? (
        <div className="space-y-2">
          {perms.allowed.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t('bots.allowedTools')}</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {perms.allowed.map((p) => (
                  <span key={p} className="rounded-md border border-border/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">{p}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">{t('bots.capabilitiesUnavailable')}</p>
      )}
    </div>
  );
}

function SettingsSection({ bot }: { bot: AutomationView }) {
  const t = useT();
  const limits = bot.limits;
  const anyLimit = limits.maxRuntimeS != null || limits.maxTokens != null || limits.maxCost != null || limits.maxToolCalls != null;
  return (
    <div className="space-y-4 text-sm">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t('bots.budget')}</div>
        {anyLimit ? (
          <ul className="mt-1 space-y-0.5 text-xs text-foreground">
            {limits.maxRuntimeS != null && <li>Max runtime: {limits.maxRuntimeS}s</li>}
            {limits.maxTokens != null && <li>Max tokens: {limits.maxTokens}</li>}
            {limits.maxCost != null && <li>Max cost: {limits.maxCost}</li>}
            {limits.maxToolCalls != null && <li>Max tool calls: {limits.maxToolCalls}</li>}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-muted-foreground">{t('bots.noBudget')}</p>
        )}
      </div>
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t('bots.retryPolicy')}</div>
        <p className="mt-1 text-xs text-muted-foreground">
          {t('bots.maxAttempts')}: {bot.retry.maxAttempts} · {bot.retry.jitter ? 'jittered' : 'fixed'} backoff
        </p>
      </div>
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t('bots.notifications')}</div>
        <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
          <li>{t('bots.notifyOnSuccess')}: {bot.delivery.onSuccess ? 'on' : 'off'}</li>
          <li>{t('bots.notifyOnFailure')}: {bot.delivery.onFailure ? 'on' : 'off'}</li>
          <li>{t('bots.deliveryAdapter')}: {bot.delivery.adapter}</li>
        </ul>
      </div>
    </div>
  );
}
