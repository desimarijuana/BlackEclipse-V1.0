'use client';

// ── Bot chat ─────────────────────────────────────────────────────────────────
// The bot workspace's main surface: a conversation WITH the bot. You can rename
// it and edit its purpose inline, chat with it (real agent turns through
// `/api/harness/chat`, with the bot's identity + instructions as standing
// context), run it as an autonomous task now, and open Details for its schedule,
// capabilities, memory and full run history. Modeled on Grok/Hermes bots.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import {
  ArrowLeft, ArrowUp, CalendarDays, Loader2, Pause, Play,
  Settings, SquarePen,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { BotDetail } from '@/components/bots/bot-detail';
import { BreakerPill, LifecyclePill } from '@/components/bots/status-pill';
import {
  pauseAutomation, resumeAutomation, updateAutomation,
  type AutomationView,
} from '@/lib/harness/automation-browser';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { useBotChatStore, useHydrateBotChat, type BotMessage } from '@/lib/bots/chat-store';
import { formatDateTime, formatRelative, scheduleSummary } from '@/lib/bots/state';

export interface BotChatProps {
  bot: AutomationView;
  busy: boolean;
  refreshKey?: number;
  onClose: () => void;
  onChanged: () => void;
  onRunNow: (bot: AutomationView) => void;
  onDuplicate: (bot: AutomationView) => void;
  onDelete: (bot: AutomationView) => void;
}

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// A module-level empty array so the zustand selector returns a STABLE reference
// when a bot has no messages yet. Returning `?? []` inline creates a new array
// every render, which breaks useSyncExternalStore's snapshot caching and throws
// "Maximum update depth exceeded".
const NO_MESSAGES: BotMessage[] = [];

export function BotChat({
  bot, busy, refreshKey = 0, onClose, onChanged, onRunNow, onDuplicate, onDelete,
}: BotChatProps) {
  const t = useT();
  useHydrateBotAvatars();
  useHydrateBotChat();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const messages = useBotChatStore((s) => s.byBot[bot.id] ?? NO_MESSAGES);
  const append = useBotChatStore((s) => s.append);
  const clearMessages = useBotChatStore((s) => s.clear);

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [editingIdentity, setEditingIdentity] = useState(false);
  const [name, setName] = useState(bot.name);
  const [description, setDescription] = useState(bot.description ?? '');
  const [savingIdentity, setSavingIdentity] = useState(false);
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setName(bot.name);
    setDescription(bot.description ?? '');
  }, [bot.id, bot.name, bot.description]);

  const instructions = bot.action.objective ?? bot.description ?? '';
  const dirty = name.trim() !== bot.name || description.trim() !== (bot.description ?? '');

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages.length, sending, scrollToBottom]);

  const saveIdentity = useCallback(async () => {
    if (savingIdentity) return;
    if (!name.trim()) return;
    setSavingIdentity(true);
    setIdentityError(null);
    try {
      await updateAutomation(bot.id, { name: name.trim(), description: description.trim() });
      setEditingIdentity(false);
      onChanged();
    } catch (err) {
      setIdentityError(err instanceof Error ? err.message : 'save failed');
    } finally {
      setSavingIdentity(false);
    }
  }, [savingIdentity, name, description, bot.id, onChanged]);

  const doAction = useCallback(
    async (fn: () => Promise<unknown>) => {
      setActionBusy(true);
      setActionError(null);
      try {
        await fn();
        onChanged();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : 'action failed');
      } finally {
        setActionBusy(false);
      }
    },
    [onChanged],
  );

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    append(bot.id, { id: newId(), role: 'user', content: text, at: new Date().toISOString() });
    setInput('');
    setSending(true);
    // Standing context: the bot's identity + instructions, then the recent turns.
    const persona =
      `You are the persistent bot "${bot.name}" (id: ${bot.id}). ` +
      `Purpose: ${bot.description || '—'}. Standing instructions: ${instructions || '—'}. ` +
      `Answer as this bot, and use your tools to act when the user asks.`;
    const history = [
      { role: 'user' as const, content: persona },
      { role: 'assistant' as const, content: 'Understood — I am this bot.' },
      ...messages
        .filter((m) => !m.error)
        .slice(-10)
        .map((m) => ({ role: m.role, content: m.content })),
    ];
    try {
      const res = await fetch('/api/harness/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text, history, chatId: `bot-${bot.id}` }),
      });
      const payload = (await res.json().catch(() => ({}))) as { content?: string; error?: string };
      if (!res.ok || !payload.content) {
        append(bot.id, {
          id: newId(), role: 'assistant', at: new Date().toISOString(),
          content: payload.error ?? `The bot could not respond (${res.status}).`, error: true,
        });
      } else {
        append(bot.id, { id: newId(), role: 'assistant', content: payload.content, at: new Date().toISOString() });
      }
    } catch (err) {
      append(bot.id, {
        id: newId(), role: 'assistant', at: new Date().toISOString(),
        content: err instanceof Error ? err.message : 'network error', error: true,
      });
    } finally {
      setSending(false);
    }
  }, [input, sending, append, bot.id, bot.name, bot.description, instructions, messages]);

  const lastRun = useMemo(() => bot.lastRunAt, [bot.lastRunAt]);
  const spec = avatarFor(avatars, bot.id);

  return (
    <div className="glass-card flex h-full min-h-0 flex-col rounded-2xl">
      {/* Header — bot identity + autonomous controls */}
      <div className="flex items-start gap-3 border-b border-border/10 p-4">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/10 hover:text-foreground lg:hidden"
          aria-label={t('common.close')}
        >
          <ArrowLeft size={16} />
        </button>
        <button
          type="button"
          onClick={() => setDetailsOpen(true)}
          title={t('bots.customize')}
          className="shrink-0 rounded-2xl transition-transform hover:scale-105"
        >
          <BotAvatar botId={bot.id} spec={spec} size={52} title={bot.name} />
        </button>

        <div className="min-w-0 flex-1">
          {editingIdentity ? (
            <div className="space-y-2">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-label={t('bots.create.name')}
                placeholder={t('bots.namePlaceholder')}
                className="h-9 text-sm font-semibold"
                autoFocus
              />
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                aria-label={t('bots.create.purpose')}
                placeholder={t('bots.objectivePlaceholder')}
                className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
              />
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={saveIdentity} disabled={savingIdentity || !name.trim() || !dirty}>
                  {savingIdentity ? t('bots.saving') : t('bots.save')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setName(bot.name);
                    setDescription(bot.description ?? '');
                    setEditingIdentity(false);
                    setIdentityError(null);
                  }}
                >
                  {t('bots.cancelEdit')}
                </Button>
                {identityError && <span className="text-xs text-rose-300">{identityError}</span>}
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="truncate text-base font-semibold">{bot.name}</h2>
                <button
                  type="button"
                  onClick={() => setEditingIdentity(true)}
                  className="rounded-md p-0.5 text-muted-foreground hover:bg-white/10 hover:text-foreground"
                  aria-label={t('bots.edit')}
                  title={t('bots.edit')}
                >
                  <SquarePen size={13} />
                </button>
                <LifecyclePill state={bot.state} />
                {bot.breaker !== 'closed' && <BreakerPill state={bot.breaker} />}
              </div>
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                {bot.description || t('bots.emptyBody')}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <CalendarDays size={11} /> {scheduleSummary(bot.trigger)}
                </span>
                {bot.nextRunAt && (
                  <span>{t('bots.nextRun')}: <span className="text-foreground/80">{formatRelative(bot.nextRunAt)}</span></span>
                )}
                <span>
                  {t('bots.lastRun')}: {lastRun ? formatRelative(lastRun) : t('bots.never')}
                </span>
              </div>
            </>
          )}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              disabled={busy || actionBusy || bot.state !== 'active'}
              onClick={() => onRunNow(bot)}
            >
              <Play size={13} /> {t('bots.runNow')}
            </Button>
            {bot.state === 'active' ? (
              <Button
                size="icon-sm"
                variant="outline"
                disabled={actionBusy}
                title={t('bots.pause')}
                aria-label={t('bots.pause')}
                onClick={() => doAction(() => pauseAutomation(bot.id))}
              >
                <Pause size={14} />
              </Button>
            ) : bot.state === 'paused' ? (
              <Button
                size="icon-sm"
                variant="outline"
                disabled={actionBusy}
                title={t('bots.resume')}
                aria-label={t('bots.resume')}
                onClick={() => doAction(() => resumeAutomation(bot.id))}
              >
                <Play size={14} />
              </Button>
            ) : null}
            <Button
              size="icon-sm"
              variant="ghost"
              title={t('bots.detail.settings')}
              aria-label={t('bots.detail.settings')}
              onClick={() => setDetailsOpen(true)}
            >
              <Settings size={14} />
            </Button>
          </div>
          {actionError && <span className="text-[10px] text-rose-300">{actionError}</span>}
        </div>
      </div>

      {/* Thread */}
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5">
        {messages.length === 0 && (
          <div className="mx-auto max-w-md py-8 text-center">
            <BotAvatar botId={bot.id} spec={spec} size={64} className="mx-auto" />
            <p className="mt-3 text-sm font-medium">{bot.name}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {instructions || t('bots.emptyBody')}
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <SuggestionChip label="Summarize what you can do" onPick={setInput} />
              <SuggestionChip label="Run your task now" onPick={setInput} />
              <SuggestionChip label="Change your schedule" onPick={setInput} />
            </div>
          </div>
        )}

        {messages.map((m) => (
          <ChatBubble key={m.id} message={m} botId={bot.id} botName={bot.name} spec={spec} />
        ))}

        {sending && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 size={14} className="animate-spin" />
            {bot.name} is thinking…
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-border/10 p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={1}
            data-bot-composer="true"
            placeholder={`Message ${bot.name}…`}
            aria-label={`Message ${bot.name}`}
            className="max-h-40 min-h-10 flex-1 resize-none rounded-xl border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
          />
          <Button size="icon" onClick={() => void send()} disabled={sending || !input.trim()} aria-label={`Message ${bot.name}`}>
            <ArrowUp size={15} />
          </Button>
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted-foreground">
          <span>{t('bots.schedule')}: {scheduleSummary(bot.trigger)}</span>
          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => clearMessages(bot.id)}
              className="hover:text-foreground"
            >
              {t('bots.chat.clear')}
            </button>
          )}
        </div>
      </div>

      {/* Details drawer — schedule, capabilities, memory, history, settings. */}
      <Sheet open={detailsOpen} onOpenChange={setDetailsOpen}>
        <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-3xl">
          <div className="h-full p-4">
            <BotDetail
              bot={bot}
              busy={busy}
              refreshKey={refreshKey}
              onClose={() => setDetailsOpen(false)}
              onChanged={onChanged}
              onRunNow={onRunNow}
              onDuplicate={onDuplicate}
              onDelete={(b) => { setDetailsOpen(false); onDelete(b); }}
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function SuggestionChip({ label, onPick }: { label: string; onPick: (v: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onPick(label)}
      className="rounded-full border border-border/50 px-3 py-1 text-[11px] text-muted-foreground hover:border-border hover:text-foreground"
    >
      {label}
    </button>
  );
}

function ChatBubble({
  message,
  botId,
  botName,
  spec,
}: {
  message: BotMessage;
  botId: string;
  botName: string;
  spec: import('@/lib/bots/ghost').GhostSpec;
}) {
  const isUser = message.role === 'user';
  return (
    <div className={cn('flex gap-2.5', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {!isUser && <BotAvatar botId={botId} spec={spec} size={28} className="mt-0.5 shrink-0" />}
      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-3.5 py-2 text-sm',
          isUser
            ? 'bg-white/[0.08] text-foreground'
            : message.error
              ? 'border border-rose-500/30 bg-rose-500/5 text-rose-200'
              : 'glass-card-subtle text-foreground',
        )}
      >
        {!isUser && <div className="mb-0.5 text-[10px] font-semibold text-muted-foreground">{botName}</div>}
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
        <div className="mt-1 text-[10px] text-muted-foreground">{formatDateTime(message.at)}</div>
      </div>
    </div>
  );
}
