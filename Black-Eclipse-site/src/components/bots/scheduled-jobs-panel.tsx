'use client';

// ── Scheduled jobs panel ──────────────────────────────────────────────────────
// The Bots workspace's right rail: every bot that runs on a schedule (or once),
// soonest first. Reads the SAME automation list the workspace uses, so the panel
// and the bots list can never disagree. Pause/resume go through the real API.

import { useCallback, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { CalendarDays, ChevronRight, Clock, Pause, Play, Plus } from '@/lib/icons';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { useBotsStore } from '@/lib/bots/bots-store';
import { pauseAutomation, resumeAutomation, type AutomationView } from '@/lib/harness/automation-browser';
import { formatRelative, scheduleSummary, triggerClass } from '@/lib/bots/state';

export interface ScheduledJobsPanelProps {
  /** Open the New bot dialog (its Advanced section holds the schedule builder). */
  onCreate: () => void;
  onSelectBot: (id: string) => void;
  /** Collapse the rail to the right edge, when provided. */
  onCollapse?: () => void;
  /** Hosted inside a dock that already provides the glass frame (no own card). */
  bare?: boolean;
}

export function ScheduledJobsPanel({ onCreate, onSelectBot, onCollapse, bare = false }: ScheduledJobsPanelProps) {
  const t = useT();
  useHydrateBotAvatars();
  const bots = useBotsStore((s) => s.bots);
  const hydrate = useBotsStore((s) => s.hydrate);
  const avatars = useBotAvatarStore((s) => s.avatars);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const scheduled = useMemo(
    () => bots.filter((b) => triggerClass(b.trigger.type) !== 'manual' || Boolean(b.nextRunAt)),
    [bots],
  );

  const ordered = useMemo(() => {
    const withNext = scheduled.filter((b) => b.nextRunAt);
    const rest = scheduled.filter((b) => !b.nextRunAt);
    withNext.sort((a, b) => new Date(a.nextRunAt ?? 0).getTime() - new Date(b.nextRunAt ?? 0).getTime());
    return [...withNext, ...rest];
  }, [scheduled]);

  const toggle = useCallback(
    async (bot: AutomationView) => {
      setBusyId(bot.id);
      setActionError(null);
      try {
        if (bot.state === 'active') await pauseAutomation(bot.id);
        else await resumeAutomation(bot.id);
        await hydrate();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : 'action failed');
      } finally {
        setBusyId(null);
      }
    },
    [hydrate],
  );

  return (
    <div className={bare ? 'flex h-full min-h-0 flex-col' : 'glass-card flex h-full min-h-0 flex-col rounded-2xl p-4'}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{t('bots.jobsPanel.title')}</h2>
          <p className="text-[11px] text-muted-foreground">{t('bots.jobsPanel.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={onCreate}
          title={t('bots.jobsPanel.create')}
          aria-label={t('bots.jobsPanel.create')}
          className="glass-card-subtle flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground cursor-pointer"
        >
          <Plus size={14} />
        </button>
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            title={t('bots.jobsPanel.collapse')}
            aria-label={t('bots.jobsPanel.collapse')}
            className="glass-card-subtle flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground cursor-pointer"
          >
            <ChevronRight size={14} />
          </button>
        )}
      </div>

      {actionError && (
        <p className="mb-2 rounded-lg border border-rose-500/30 bg-rose-500/5 px-2 py-1.5 text-[10px] text-rose-300">
          {actionError}
        </p>
      )}

      {ordered.length === 0 ? (
        <button
          type="button"
          onClick={onCreate}
          className="flex flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border/40 px-3 py-6 text-center text-[11px] text-muted-foreground hover:border-border hover:text-foreground"
        >
          <CalendarDays size={18} />
          {t('bots.jobsPanel.empty')}
          <span className="font-semibold text-foreground">{t('bots.jobsPanel.create')}</span>
        </button>
      ) : (
        <ul className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-0.5">
          {ordered.map((bot) => (
            <li key={bot.id}>
              <div className="glass-card-subtle flex items-center gap-2.5 rounded-xl px-2.5 py-2">
                <button
                  type="button"
                  onClick={() => onSelectBot(bot.id)}
                  className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                  title={bot.name}
                >
                  <BotAvatar botId={bot.id} spec={avatarFor(avatars, bot.id)} size={28} title={bot.name} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold text-foreground">{bot.name}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                      {scheduleSummary(bot.trigger)}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                      <Clock size={10} />
                      {bot.nextRunAt
                        ? <>{t('bots.nextRun')}: <span className="text-foreground/80">{formatRelative(bot.nextRunAt)}</span></>
                        : t('bots.jobsPanel.notScheduled')}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  disabled={busyId === bot.id}
                  onClick={() => void toggle(bot)}
                  title={bot.state === 'active' ? t('bots.jobsPanel.pause') : t('bots.jobsPanel.resume')}
                  aria-label={bot.state === 'active' ? t('bots.jobsPanel.pause') : t('bots.jobsPanel.resume')}
                  className={cn(
                    'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-white/10 hover:text-foreground disabled:opacity-40',
                  )}
                >
                  {bot.state === 'active' ? <Pause size={13} /> : <Play size={13} />}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
