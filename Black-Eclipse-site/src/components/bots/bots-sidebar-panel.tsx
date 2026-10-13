'use client';

// The sidebar's bot list — shown while the Bots mode is active, exactly as chat
// history is shown under ChatBot. Lists the user's REAL bots (the shared bot
// store) plus their group chats, and opens one on click. Collapsed to avatars
// when the sidebar is narrow. This is the ONE bot list: the Bots page itself is
// just the conversation + the scheduled-jobs rail.

import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { Loader2, Plus, RefreshCw, Sparkles, Users } from '@/lib/icons';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { lifecycleTone } from '@/components/bots/status-pill';
import { useBotsStore } from '@/lib/bots/bots-store';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { useBotGroupsStore, useHydrateBotGroups } from '@/lib/bots/groups-store';
import { FINANCE_GROUP_NAME, useSeedFinancePack } from '@/lib/bots/finance-bots';
import { ghostSpecFromId } from '@/lib/bots/ghost';
import { executionLabel, isLiveExecution, type Tone } from '@/lib/bots/state';

const DOT: Record<Tone, string> = {
  positive: 'bg-emerald-400',
  warning: 'bg-amber-400',
  danger: 'bg-rose-400',
  info: 'bg-sky-400',
  muted: 'bg-muted-foreground/50',
};

export interface BotsSidebarPanelProps {
  collapsed: boolean;
  /** Switch to the Bots tab (the store selection is set here, too). */
  onActivate: () => void;
}

export function BotsSidebarPanel({ collapsed, onActivate }: BotsSidebarPanelProps) {
  const t = useT();
  useHydrateBotAvatars();
  useHydrateBotGroups();
  const bots = useBotsStore((s) => s.bots);
  const loading = useBotsStore((s) => s.loading);
  const selectedId = useBotsStore((s) => s.selectedId);
  const selectedGroupId = useBotsStore((s) => s.selectedGroupId);
  const statusById = useBotsStore((s) => s.statusById);
  const select = useBotsStore((s) => s.select);
  const selectGroup = useBotsStore((s) => s.selectGroup);
  const hydrate = useBotsStore((s) => s.hydrate);
  const openCreate = useBotsStore((s) => s.openCreate);
  const openGroupCreate = useBotsStore((s) => s.openGroupCreate);
  const avatars = useBotAvatarStore((s) => s.avatars);
  const groups = useBotGroupsStore((s) => s.groups);
  const { seed: seedFinance, busy: seedingFinance } = useSeedFinancePack();
  const hasFinanceGroup = groups.some(
    (g) => g.name.trim().toLowerCase() === FINANCE_GROUP_NAME.toLowerCase(),
  );

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  const open = (id: string | null) => {
    select(id);
    onActivate();
  };

  const openGroup = (id: string) => {
    selectGroup(id);
    onActivate();
  };

  const startCreate = () => {
    openCreate();
    onActivate();
  };

  const startGroupCreate = () => {
    openGroupCreate();
    onActivate();
  };

  if (collapsed) {
    return (
      <div className="flex w-full flex-col items-center gap-1.5 py-2">
        <button
          type="button"
          onClick={startCreate}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground"
          title={t('bots.dialog.title')}
          aria-label={t('bots.dialog.title')}
        >
          <Plus size={16} />
        </button>
        <button
          type="button"
          onClick={() => void seedFinance()}
          disabled={seedingFinance}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
          title={t('bots.finance.seed')}
          aria-label={t('bots.finance.seed')}
        >
          {seedingFinance ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
        </button>
        {bots.slice(0, 12).map((bot) => {
          const live = statusById[bot.id]?.lastExecution;
          const active = bot.id === selectedId;
          return (
            <button
              key={bot.id}
              type="button"
              onClick={() => open(bot.id)}
              title={bot.name}
              aria-label={bot.name}
              className={cn(
                'relative flex h-9 w-9 items-center justify-center rounded-xl transition-colors',
                active ? 'bg-white/[0.08]' : 'hover:bg-accent/60',
              )}
            >
              <BotAvatar botId={bot.id} spec={avatarFor(avatars, bot.id)} size={24} title={bot.name} />
              {live && isLiveExecution(live.state) && (
                <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-sky-400" />
              )}
            </button>
          );
        })}
        {groups.slice(0, 6).map((g) => (
          <button
            key={g.id}
            type="button"
            onClick={() => openGroup(g.id)}
            title={g.name}
            aria-label={g.name}
            className={cn(
              'relative flex h-9 w-9 items-center justify-center rounded-xl transition-colors',
              g.id === selectedGroupId ? 'bg-white/[0.08]' : 'hover:bg-accent/60',
            )}
          >
            {g.image ? (
              <img src={g.image} alt="" className="h-6 w-6 rounded-full object-cover" />
            ) : (
              <GhostAvatar spec={ghostSpecFromId(g.id)} size={24} />
            )}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-2 flex items-center justify-between gap-2 px-1">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          {t('bots.title')} · {bots.length}
        </span>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => void seedFinance()}
            disabled={seedingFinance}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
            title={t('bots.finance.seed')}
            aria-label={t('bots.finance.seed')}
          >
            {seedingFinance ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
          </button>
          <button
            type="button"
            onClick={startCreate}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            title={t('bots.dialog.title')}
            aria-label={t('bots.dialog.title')}
          >
            <Plus size={13} />
          </button>
          <button
            type="button"
            onClick={() => void hydrate()}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            title={t('common.reset')}
            aria-label={t('common.reset')}
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {loading && bots.length === 0 ? (
        <p className="px-2 py-1 text-xs text-muted-foreground">{t('common.loading')}</p>
      ) : bots.length === 0 ? (
        <button
          type="button"
          onClick={startCreate}
          className="mx-1 rounded-xl border border-dashed border-border/50 px-3 py-4 text-left text-xs text-muted-foreground hover:border-border hover:text-foreground"
        >
          {t('bots.empty')}
        </button>
      ) : (
        <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto scrollbar-hide">
          {bots.map((bot) => {
            const active = bot.id === selectedId;
            const status = statusById[bot.id];
            const live = status?.lastExecution;
            const tone = live ? (isLiveExecution(live.state) ? 'info' : lifecycleTone(bot.state)) : lifecycleTone(bot.state);
            const subtitle = live
              ? executionLabel(live.state)
              : bot.state === 'active'
                ? t('bots.state.active')
                : bot.state;
            return (
              <li key={bot.id}>
                <button
                  type="button"
                  onClick={() => open(bot.id)}
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left transition-colors',
                    active ? 'bg-white/[0.08] text-foreground' : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
                  )}
                >
                  <BotAvatar botId={bot.id} spec={avatarFor(avatars, bot.id)} size={26} title={bot.name} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold">{bot.name}</span>
                    <span className="block truncate text-[10px] capitalize opacity-80">{subtitle}</span>
                  </span>
                  <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', DOT[tone])} aria-hidden />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {/* Finance starter pack — a labeled, always-findable entry point while the
          group room does not exist yet. */}
      {!hasFinanceGroup && (
        <button
          type="button"
          onClick={() => void seedFinance()}
          disabled={seedingFinance}
          className="mx-1 mt-2 flex w-[calc(100%-0.5rem)] items-center justify-center gap-1.5 rounded-xl border border-dashed border-primary/30 bg-primary/5 px-2 py-2 text-[11px] font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
        >
          {seedingFinance ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          {seedingFinance ? t('bots.finance.seeding') : t('bots.finance.seed')}
        </button>
      )}

      {/* Group chats */}
      <div className="mt-3 border-t border-border/10 pt-2">
        <div className="mb-1 flex items-center justify-between gap-2 px-1">
          <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            <Users size={11} /> {t('bots.groups.title')}
          </span>
          <button
            type="button"
            onClick={startGroupCreate}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            title={t('bots.groups.new')}
            aria-label={t('bots.groups.new')}
          >
            <Plus size={12} />
          </button>
        </div>
        {groups.length === 0 ? (
          <button
            type="button"
            onClick={startGroupCreate}
            className="mx-1 w-[calc(100%-0.5rem)] rounded-xl border border-dashed border-border/40 px-2 py-2 text-left text-[10px] text-muted-foreground hover:border-border hover:text-foreground"
          >
            {t('bots.groups.empty')}
          </button>
        ) : (
          <ul className="space-y-0.5">
            {groups.map((g) => {
              const active = g.id === selectedGroupId;
              return (
                <li key={g.id}>
                  <button
                    type="button"
                    onClick={() => openGroup(g.id)}
                    className={cn(
                      'flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left transition-colors',
                      active ? 'bg-white/[0.08] text-foreground' : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
                    )}
                  >
                    {g.image ? (
                      <img src={g.image} alt="" className="h-6 w-6 shrink-0 rounded-full object-cover" />
                    ) : (
                      <GhostAvatar spec={ghostSpecFromId(g.id)} size={26} />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-semibold">{g.name}</span>
                      <span className="block truncate text-[10px] opacity-80">
                        {t('bots.groups.members', { count: g.memberIds.length })}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
