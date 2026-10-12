'use client';

// The sidebar's bot list — shown while the Bots mode is active, exactly as chat
// history is shown under ChatBot. Lists the user's REAL bots (the shared bot
// store) and opens one on click. Collapsed to avatars when the sidebar is narrow.

import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { Plus, RefreshCw } from '@/lib/icons';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { lifecycleTone } from '@/components/bots/status-pill';
import { useBotsStore } from '@/lib/bots/bots-store';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
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
  const bots = useBotsStore((s) => s.bots);
  const loading = useBotsStore((s) => s.loading);
  const selectedId = useBotsStore((s) => s.selectedId);
  const statusById = useBotsStore((s) => s.statusById);
  const select = useBotsStore((s) => s.select);
  const hydrate = useBotsStore((s) => s.hydrate);
  const openCreate = useBotsStore((s) => s.openCreate);
  const avatars = useBotAvatarStore((s) => s.avatars);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  const open = (id: string | null) => {
    select(id);
    onActivate();
  };

  const startCreate = () => {
    openCreate();
    onActivate();
  };

  if (collapsed) {
    return (
      <div className="flex w-full flex-col items-center gap-1.5 py-2">
        <button
          type="button"
          onClick={startCreate}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground"
          title={t('bots.createBot')}
          aria-label={t('bots.createBot')}
        >
          <Plus size={16} />
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
              <GhostAvatar spec={avatarFor(avatars, bot.id)} size={24} />
              {live && isLiveExecution(live.state) && (
                <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-sky-400" />
              )}
            </button>
          );
        })}
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
            onClick={startCreate}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            title={t('bots.createBot')}
            aria-label={t('bots.createBot')}
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
                  <GhostAvatar spec={avatarFor(avatars, bot.id)} size={26} />
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
    </div>
  );
}
