'use client';

// ── Bots workspace ───────────────────────────────────────────────────────────
// Discover, create and manage persistent autonomous agents. A bot is a real
// Automation in the Python runtime (a `run_agent` action on a trigger); it keeps
// running in the durable backend scheduler after the browser closes. The list,
// filters, detail view, run history and every control read and write REAL
// persisted state through `/api/automations`.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/i18n';
import {
  CalendarDays, Plus, RefreshCw, Search, Sparkles, X,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { TabBar } from '@/components/ui/tab-bar';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { BotCard, type BotMenuAction } from '@/components/bots/bot-card';
import { BotChat } from '@/components/bots/bot-chat';
import { CreateBot } from '@/components/bots/create-bot';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import {
  createAutomation, deleteAutomation, disableAutomation, enableAutomation,
  pauseAutomation, resumeAutomation, runAutomationNow,
  type AutomationView, type AutomationStatusView, type ExecutionView,
} from '@/lib/harness/automation-browser';
import { useBotsStore } from '@/lib/bots/bots-store';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import {
  BOT_FILTERS, botMatchesFilter, botMatchesSearch, isLiveExecution,
  type BotFilter,
} from '@/lib/bots/state';

const EXAMPLE_KEYS: TranslationKey[] = [
  'bots.example.marketBrief',
  'bots.example.portfolioRisk',
  'bots.example.watchlist',
  'bots.example.dataQuality',
  'bots.example.researchAssistant',
];

function lastExecution(status: AutomationStatusView | undefined): ExecutionView | undefined {
  return status?.lastExecution ?? undefined;
}

export function BotsScreen() {
  const t = useT();
  useHydrateBotAvatars();

  const bots = useBotsStore((s) => s.bots);
  const statusById = useBotsStore((s) => s.statusById);
  const loading = useBotsStore((s) => s.loading);
  const error = useBotsStore((s) => s.error);
  const selectedId = useBotsStore((s) => s.selectedId);
  const hydrate = useBotsStore((s) => s.hydrate);
  const select = useBotsStore((s) => s.select);
  const createOpen = useBotsStore((s) => s.createOpen);
  const openCreate = useBotsStore((s) => s.openCreate);
  const setCreateOpen = useBotsStore((s) => s.setCreateOpen);

  const [filter, setFilter] = useState<BotFilter>('all');
  const [query, setQuery] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AutomationView | null>(null);
  const [runKey, setRunKey] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);

  // Initial load + a slow refresh so the list stays current across tabs.
  useEffect(() => {
    void hydrate();
    const timer = setInterval(() => void hydrate(), 20000);
    return () => clearInterval(timer);
  }, [hydrate]);

  // Deep link: /?tab=bots&bot=<id> (read once on mount).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const id = new URLSearchParams(window.location.search).get('bot');
    if (id) select(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedBot = useMemo(() => bots.find((b) => b.id === selectedId) ?? null, [bots, selectedId]);

  const runningIds = useMemo(() => {
    const set = new Set<string>();
    for (const status of Object.values(statusById)) {
      const last = lastExecution(status);
      if (last && isLiveExecution(last.state)) set.add(status.automationId);
    }
    return set;
  }, [statusById]);

  const filtered = useMemo(
    () => bots.filter((b) => botMatchesSearch(b, query) && botMatchesFilter(b, filter, runningIds)),
    [bots, query, filter, runningIds],
  );

  const openBot = useCallback(
    (id: string | null) => {
      select(id);
    },
    [select],
  );

  const runAction = useCallback(
    async (id: string, fn: () => Promise<unknown>) => {
      setBusyId(id);
      setActionError(null);
      try {
        await fn();
        await hydrate();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : 'action failed');
      } finally {
        setBusyId(null);
      }
    },
    [hydrate],
  );

  const runNow = useCallback(
    (bot: AutomationView) => {
      setRunKey((k) => k + 1);
      return runAction(bot.id, () => runAutomationNow(bot.id));
    },
    [runAction],
  );

  const handleMenu = useCallback(
    (bot: AutomationView, action: BotMenuAction) => {
      switch (action) {
        case 'run':
          return runNow(bot);
        case 'pause':
          return runAction(bot.id, () => pauseAutomation(bot.id));
        case 'resume':
          return runAction(bot.id, () => resumeAutomation(bot.id));
        case 'enable':
          return runAction(bot.id, () => enableAutomation(bot.id));
        case 'disable':
          return runAction(bot.id, () => disableAutomation(bot.id));
        case 'history':
          return openBot(bot.id);
        case 'edit':
          return openBot(bot.id);
        case 'duplicate':
          return runAction(bot.id, () => duplicateBot(bot));
        case 'delete':
          setDeleteTarget(bot);
          return;
      }
    },
    [openBot, runAction, runNow],
  );

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setDeleteTarget(null);
    if (selectedId === id) openBot(null);
    await runAction(id, () => deleteAutomation(id));
  }, [deleteTarget, selectedId, openBot, runAction]);

  const onCreateWithChat = useCallback((prefill: string) => {
    const prompt = prefill.trim()
      ? `Create a bot for me: ${prefill.trim()}`
      : 'Create a bot for me. Ask me what it should do.';
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('be:ask-eclipse', { detail: { prompt } }));
    }
    setCreateOpen(false);
  }, [setCreateOpen]);

  const showDetail = Boolean(selectedBot);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8">
      {/* A. Workspace header */}
      <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold">{t('bots.title')}</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">{t('bots.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => onCreateWithChat('')}>
            <Sparkles size={14} /> {t('bots.createWithChat')}
          </Button>
          <Button onClick={openCreate}>
            <Plus size={14} /> {t('bots.createBot')}
          </Button>
        </div>
      </header>

      {(actionError || error) && (
        <div className="glass-card-subtle mb-4 flex items-center gap-2 rounded-lg border border-rose-500/30 px-3 py-2 text-sm text-rose-300">
          <span className="flex-1">{actionError || error}</span>
          <button type="button" onClick={() => { setActionError(null); void hydrate(); }} className="text-xs underline">
            {t('common.reset')}
          </button>
        </div>
      )}

      <div className={cn('grid gap-5', showDetail ? 'lg:grid-cols-[minmax(0,24rem)_1fr]' : 'grid-cols-1')}>
        {/* B. Collection + C. Filters */}
        <div className={cn('min-w-0', showDetail && 'hidden lg:block')}>
          {createOpen ? (
            <CreateBot
              existingNames={bots.map((b) => b.name)}
              onCreated={(bot) => { setCreateOpen(false); openBot(bot.id); void hydrate(); }}
              onRunNow={(bot) => { void runNow(bot); setCreateOpen(false); openBot(bot.id); }}
              onClose={() => setCreateOpen(false)}
              onCreateWithChat={onCreateWithChat}
            />
          ) : (
            <>
              <div className="mb-3 flex items-center gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={t('bots.search')}
                    className="pl-8"
                    aria-label={t('bots.search')}
                  />
                  {query && (
                    <button
                      type="button"
                      onClick={() => setQuery('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
                      aria-label={t('common.reset')}
                    >
                      <X size={13} />
                    </button>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => void hydrate()}
                  className="rounded-lg p-2 text-muted-foreground hover:bg-white/10 hover:text-foreground"
                  aria-label={t('common.reset')}
                  title="Refresh"
                >
                  <RefreshCw size={15} />
                </button>
              </div>

              <TabBar
                variant="subtle"
                wrap
                className="mb-3"
                items={BOT_FILTERS.map((f) => ({ id: f.id, label: t(f.labelKey as TranslationKey) }))}
                activeId={filter}
                onChange={(id) => setFilter(id as BotFilter)}
              />

              {loading ? (
                <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
              ) : bots.length === 0 ? (
                <EmptyState onCreate={openCreate} onCreateWithChat={() => onCreateWithChat('')} />
              ) : filtered.length === 0 ? (
                <p className="glass-card rounded-2xl p-6 text-center text-sm text-muted-foreground">
                  {t('bots.noMatches')}
                </p>
              ) : (
                <>
                  <p className="mb-2 text-xs text-muted-foreground">
                    {t('bots.resultCount', { count: filtered.length })}
                  </p>
                  <ul className="space-y-2.5">
                    {filtered.map((bot) => (
                      <BotCard
                        key={bot.id}
                        bot={bot}
                        execution={lastExecution(statusById[bot.id])}
                        selected={bot.id === selectedId}
                        busy={busyId === bot.id}
                        onOpen={() => openBot(bot.id)}
                        onAction={(a) => handleMenu(bot, a)}
                      />
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </div>

        {/* The selected bot opens as a conversation (chat-first), not an admin
            panel. Schedule, capabilities and history live behind Details. */}
        {showDetail && selectedBot && (
          <div className="min-h-0">
            <div className="h-[calc(100vh-11rem)]">
              <BotChat
                bot={selectedBot}
                busy={busyId === selectedBot.id}
                onClose={() => openBot(null)}
                onChanged={() => void hydrate()}
                onRunNow={(bot) => runNow(bot)}
                refreshKey={runKey}
                onDuplicate={(bot) => runAction(bot.id, () => duplicateBot(bot))}
                onDelete={(bot) => setDeleteTarget(bot)}
              />
            </div>
          </div>
        )}
      </div>

      {/* Delete confirmation — destructive, with the real consequence stated. */}
      <Dialog open={Boolean(deleteTarget)} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('bots.delete')}</DialogTitle>
            <DialogDescription>
              {t('bots.deleteConfirm')} {deleteTarget ? `“${deleteTarget.name}”` : ''}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>{t('bots.cancel')}</Button>
            <Button variant="destructive" onClick={confirmDelete}>{t('bots.delete')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Duplicate a bot's configuration as a new PAUSED draft so it can be reviewed
 *  before it ever runs. */
async function duplicateBot(bot: AutomationView): Promise<AutomationView> {
  return createAutomation({
    name: `${bot.name} copy`,
    description: bot.description ?? bot.action.objective ?? undefined,
    state: 'paused',
    trigger: {
      type: bot.trigger.type,
      cron: bot.trigger.cron,
      intervalSeconds: bot.trigger.intervalSeconds,
      runAt: bot.trigger.runAt,
      timezone: bot.trigger.timezone,
    },
    action: {
      type: bot.action.type,
      objective: bot.action.objective,
      agentId: bot.action.agentId,
    },
    tags: [...bot.tags.filter((x) => x !== 'bot'), 'bot'],
  });
}

function EmptyState({ onCreate, onCreateWithChat }: { onCreate: () => void; onCreateWithChat: () => void }) {
  const t = useT();
  const avatars = useBotAvatarStore((s) => s.avatars);
  return (
    <div className="glass-card rounded-2xl px-6 py-10 text-center">
      <div className="mx-auto mb-4 flex items-center justify-center gap-1">
        {['a', 'b', 'c'].map((k, i) => (
          <GhostAvatar key={k} spec={avatarFor(avatars, `example-${k}`)} size={i === 1 ? 56 : 40} className={i === 1 ? '' : 'opacity-70'} />
        ))}
      </div>
      <h2 className="text-base font-semibold">{t('bots.emptyTitle')}</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{t('bots.emptyBody')}</p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        <Button onClick={onCreate}>
          <Plus size={14} /> {t('bots.createBot')}
        </Button>
        <Button variant="outline" onClick={onCreateWithChat}>
          <Sparkles size={14} /> {t('bots.createWithChat')}
        </Button>
      </div>
      <div className="mx-auto mt-8 max-w-xl text-left">
        <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <CalendarDays size={13} /> {t('bots.examplesTitle')}
        </div>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {EXAMPLE_KEYS.map((key) => (
            <li key={key} className="glass-card-subtle rounded-xl px-3 py-2 text-xs text-muted-foreground">
              {t(key)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
