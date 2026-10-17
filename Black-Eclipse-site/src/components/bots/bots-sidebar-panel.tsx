'use client';

// The sidebar's bot list — shown while the Bots mode is active, exactly as chat
// history is shown under ChatBot. Lists the user's REAL bots (the shared bot
// store) plus their group chats, and opens one on click. Collapsed to avatars
// when the sidebar is narrow. This is the ONE bot list: the Bots page itself is
// just the conversation + the scheduled-jobs rail.

import { useCallback, useEffect, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { Plus, RefreshCw, Users } from '@/lib/icons';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { useBotsStore } from '@/lib/bots/bots-store';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { useBotChatStore } from '@/lib/bots/chat-store';
import { useBotGroupsStore, useHydrateBotGroups } from '@/lib/bots/groups-store';
import { ghostSpecFromId } from '@/lib/bots/ghost';
import { executionLabel, isTerminalExecution } from '@/lib/bots/state';
import type { AutomationStatusView } from '@/lib/harness/automation-browser';
import type { BotMessage } from '@/lib/bots/chat-store';

/** Most-recent activity for a bot: its last chat message, else its last run,
 *  else its last edit. Used to sort the list newest-first. */
function lastActivityMs(
  botId: string,
  fallback: string | undefined | null,
  byBot: Record<string, BotMessage[]>,
  statusById: Record<string, AutomationStatusView>,
): number {
  const msgs = byBot[botId];
  const lastMsg = msgs && msgs.length > 0 ? Date.parse(msgs[msgs.length - 1].at) : 0;
  const last = statusById[botId]?.lastExecution;
  const runAt = last ? Date.parse(last.finishedAt ?? last.startedAt) : 0;
  const edited = fallback ? Date.parse(fallback) : 0;
  return Math.max(lastMsg || 0, runAt || 0, edited || 0);
}

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
  const seenRuns = useBotsStore((s) => s.seenRuns);
  const markSeen = useBotsStore((s) => s.markSeen);
  const select = useBotsStore((s) => s.select);
  const selectGroup = useBotsStore((s) => s.selectGroup);
  const hydrate = useBotsStore((s) => s.hydrate);
  const openCreate = useBotsStore((s) => s.openCreate);
  const openGroupCreate = useBotsStore((s) => s.openGroupCreate);
  const avatars = useBotAvatarStore((s) => s.avatars);
  const groups = useBotGroupsStore((s) => s.groups);
  const byGroup = useBotGroupsStore((s) => s.byGroup);
  const byBot = useBotChatStore((s) => s.byBot);

  // The Bots workspace already refreshes the shared store on a 20s interval
  // while this panel is visible; one hydrate on mount is enough here.
  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  // A bot has an unseen message when its latest terminal run is newer than the
  // last one the operator opened. A bot never opened before is not "unread"
  // (its history is seeded silently below), so no dot flashes on first load.
  const isUnread = useCallback(
    (botId: string) => {
      const last = statusById[botId]?.lastExecution;
      if (!last) return false;
      const seen = seenRuns[botId];
      return seen !== undefined && seen !== last.id && isTerminalExecution(last.state);
    },
    [statusById, seenRuns],
  );

  // Seed the seen ledger for bots we have never opened, so existing history is
  // never mistaken for a brand-new message.
  useEffect(() => {
    for (const bot of bots) {
      const last = statusById[bot.id]?.lastExecution;
      if (last && seenRuns[bot.id] === undefined) markSeen(bot.id, last.id);
    }
  }, [bots, statusById, seenRuns, markSeen]);

  const sortedBots = useMemo(
    () => [...bots].sort((a, b) =>
      lastActivityMs(b.id, b.lastRunAt ?? b.updatedAt, byBot, statusById)
      - lastActivityMs(a.id, a.lastRunAt ?? a.updatedAt, byBot, statusById)),
    [bots, byBot, statusById],
  );

  const sortedGroups = useMemo(
    () => [...groups].sort((a, b) => {
      const am = byGroup[a.id];
      const bm = byGroup[b.id];
      const at = am && am.length > 0 ? Date.parse(am[am.length - 1].at) : Date.parse(a.createdAt);
      const bt = bm && bm.length > 0 ? Date.parse(bm[bm.length - 1].at) : Date.parse(b.createdAt);
      return (bt || 0) - (at || 0);
    }),
    [groups, byGroup],
  );

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
        {sortedBots.slice(0, 12).map((bot) => {
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
              {isUnread(bot.id) && (
                <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-primary ring-2 ring-background" />
              )}
            </button>
          );
        })}
        {sortedGroups.slice(0, 6).map((g) => (
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
          {sortedBots.map((bot) => {
            const active = bot.id === selectedId;
            const live = statusById[bot.id]?.lastExecution;
            const unread = isUnread(bot.id);
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
                    <span className={cn('block truncate text-xs', unread ? 'font-semibold text-foreground' : 'font-semibold')}>{bot.name}</span>
                    <span className="block truncate text-[10px] capitalize opacity-80">{subtitle}</span>
                  </span>
                  {unread && <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
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
            {sortedGroups.map((g) => {
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
