'use client';

// One bot in the collection list. Compact and scannable: avatar, name, purpose,
// state, trigger, next/last run. The primary interaction (Open) is a button; the
// secondary actions live in a contextual menu so the row stays uncluttered.

import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/i18n';
import { ArrowUpRight, History, MoreHorizontal, Play, Pause, Trash2, Copy, Settings } from '@/lib/icons';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { BreakerPill, ExecutionPill, LifecyclePill } from '@/components/bots/status-pill';
import type { AutomationView, ExecutionView } from '@/lib/harness/automation-client';
import { avatarFor, useBotAvatarStore } from '@/lib/bots/avatar-store';
import { formatRelative, scheduleSummary, triggerClass } from '@/lib/bots/state';

export type BotMenuAction = 'edit' | 'run' | 'pause' | 'resume' | 'enable' | 'disable' | 'history' | 'duplicate' | 'delete';

export interface BotCardProps {
  bot: AutomationView;
  execution?: ExecutionView;
  selected: boolean;
  busy: boolean;
  onOpen: () => void;
  onAction: (action: BotMenuAction) => void;
}

const TRIGGER_LABEL: Record<ReturnType<typeof triggerClass>, TranslationKey> = {
  manual: 'bots.trigger.manual',
  once: 'bots.trigger.once',
  recurring: 'bots.trigger.recurring',
  event: 'bots.trigger.event',
};

export function BotCard({ bot, execution, selected, busy, onOpen, onAction }: BotCardProps) {
  const t = useT();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const spec = avatarFor(avatars, bot.id);
  const trigger = triggerClass(bot.trigger.type);

  const canRun = bot.state === 'active';
  const canPause = bot.state === 'active';
  const canResume = bot.state === 'paused';
  const canEnable = bot.state === 'draft' || bot.state === 'validating' || bot.state === 'disabled';

  return (
    <li
      className={cn(
        'glass-card group relative rounded-2xl p-4 transition-[border-color,box-shadow]',
        selected ? 'ring-1 ring-white/25' : 'hover:ring-1 hover:ring-white/10',
      )}
    >
      <div className="flex items-start gap-3.5">
        <button
          type="button"
          onClick={onOpen}
          className="rounded-2xl transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`${t('bots.open')} ${bot.name}`}
        >
          <GhostAvatar spec={spec} size={52} />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onOpen}
              className="truncate text-sm font-semibold hover:underline focus-visible:outline-none focus-visible:underline"
            >
              {bot.name}
            </button>
            <LifecyclePill state={bot.state} />
            {execution && <ExecutionPill state={execution.state} />}
            <BreakerPill state={bot.breaker} />
          </div>

          {bot.description && (
            <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{bot.description}</p>
          )}

          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <span className="text-foreground/70">{t(TRIGGER_LABEL[trigger] as never)}</span>
              <span aria-hidden>·</span>
              {scheduleSummary(bot.trigger)}
            </span>
            {bot.nextRunAt && (
              <span>
                {t('bots.nextRun')}: <span className="text-foreground/80">{formatRelative(bot.nextRunAt)}</span>
              </span>
            )}
            <span>
              {t('bots.lastRun')}:{' '}
              <span className="text-foreground/80">
                {bot.lastRunAt ? formatRelative(bot.lastRunAt) : t('bots.never')}
              </span>
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onOpen}
            className="hidden items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-white/10 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex"
          >
            {t('bots.open')} <ArrowUpRight size={13} />
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  disabled={busy}
                  aria-label={`${t('bots.more')} — ${bot.name}`}
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/10 hover:text-foreground disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              }
            >
              <MoreHorizontal size={16} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onClick={onOpen}>
                <ArrowUpRight size={14} /> {t('bots.open')}
              </DropdownMenuItem>
              {canRun && (
                <DropdownMenuItem onClick={() => onAction('run')}>
                  <Play size={14} /> {t('bots.runNow')}
                </DropdownMenuItem>
              )}
              {canPause && (
                <DropdownMenuItem onClick={() => onAction('pause')}>
                  <Pause size={14} /> {t('bots.pause')}
                </DropdownMenuItem>
              )}
              {canResume && (
                <DropdownMenuItem onClick={() => onAction('resume')}>
                  <Play size={14} /> {t('bots.resume')}
                </DropdownMenuItem>
              )}
              {canEnable && (
                <DropdownMenuItem onClick={() => onAction('enable')}>
                  <Play size={14} /> {t('bots.enable')}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={() => onAction('edit')}>
                <Settings size={14} /> {t('bots.edit')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onAction('history')}>
                <History size={14} /> {t('bots.viewHistory')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onAction('duplicate')}>
                <Copy size={14} /> {t('bots.duplicate')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => onAction('delete')} className="text-rose-300 data-[highlighted]:text-rose-200">
                <Trash2 size={14} /> {t('bots.delete')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </li>
  );
}
