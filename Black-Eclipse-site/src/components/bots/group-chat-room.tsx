'use client';

// ── Group chat room ───────────────────────────────────────────────────────────
// A conversation shared by 2–6 bots. The user speaks to the room; the reply comes
// from the real harness with the room's member roster as standing context, and is
// attributed to the room (never to a specific bot, which we cannot guarantee).

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import {
  ArrowUp, CalendarDays, CheckCircle2, ChevronDown, Copy, Loader2, Pause, Play, Settings, Trash2, Users,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Markdown } from '@/components/chat/markdown';
import { getAgentProvider } from '@/lib/agent/registry';
import { useWorkspaceStore } from '@/lib/agent-workspace/store';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { GroupSettingsDialog } from '@/components/bots/group-settings-dialog';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import {
  useBotGroupsStore, useHydrateBotGroups, type BotGroup, type GroupMessage,
} from '@/lib/bots/groups-store';
import { ghostSpecFromId } from '@/lib/bots/ghost';
import { formatDateTime, scheduleSummary } from '@/lib/bots/state';
import {
  pauseAutomation, resumeAutomation, runAutomationNow,
  type AutomationView,
} from '@/lib/harness/automation-browser';

export interface GroupChatRoomProps {
  group: BotGroup;
  bots: AutomationView[];
  onDeleted: (id: string) => void;
  /** Refresh the bot list after a group-wide run/pause/resume. */
  onChanged?: () => void;
}

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

const NO_MESSAGES: GroupMessage[] = [];

export function GroupChatRoom({ group, bots, onDeleted, onChanged }: GroupChatRoomProps) {
  const t = useT();
  useHydrateBotAvatars();
  useHydrateBotGroups();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const messages = useBotGroupsStore((s) => s.byGroup[group.id] ?? NO_MESSAGES);
  const append = useBotGroupsStore((s) => s.appendMessage);
  const updateMessage = useBotGroupsStore((s) => s.updateMessage);
  const clearMessages = useBotGroupsStore((s) => s.clearMessages);
  const deleteGroup = useBotGroupsStore((s) => s.deleteGroup);
  // The right-docked scheduled-jobs rail is the shared Agent Workspace dock.
  const schedulerOpen = useWorkspaceStore((s) => s.open);
  const toggleScheduler = useWorkspaceStore((s) => s.toggle);

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busyAll, setBusyAll] = useState(false);
  const [groupNote, setGroupNote] = useState<string | null>(null);
  /** Who answers: 'all' (every member) or a single member's bot id. */
  const [audience, setAudience] = useState<string>('all');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const controllersRef = useRef<AbortController[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Stop any in-flight runs if the room unmounts so streams are not orphaned.
  useEffect(() => () => controllersRef.current.forEach((c) => c.abort()), []);

  const members = useMemo(
    () => group.memberIds.map((id) => bots.find((b) => b.id === id)).filter((b): b is AutomationView => Boolean(b)),
    [group.memberIds, bots],
  );

  const groupSpec = useMemo(() => ghostSpecFromId(group.id), [group.id]);

  const allActive = members.length > 0 && members.every((b) => b.state === 'active');
  useEffect(() => {
    if (!groupNote) return;
    const timer = setTimeout(() => setGroupNote(null), 6000);
    return () => clearTimeout(timer);
  }, [groupNote]);

  // Run every member's automation right now.
  const runAll = useCallback(async () => {
    if (busyAll || members.length === 0) return;
    setBusyAll(true);
    setGroupNote(null);
    try {
      await Promise.all(members.map((b) => runAutomationNow(b.id)));
      setGroupNote(t('bots.groups.ranAll'));
      onChanged?.();
    } catch (err) {
      setGroupNote(err instanceof Error ? err.message : 'run failed');
    } finally {
      setBusyAll(false);
    }
  }, [busyAll, members, onChanged, t]);

  // Pause/resume every member's automation.
  const setAllPausedState = useCallback(async (pause: boolean) => {
    if (busyAll || members.length === 0) return;
    setBusyAll(true);
    setGroupNote(null);
    try {
      await Promise.all(members.map((b) => (pause ? pauseAutomation(b.id) : resumeAutomation(b.id))));
      setGroupNote(t(pause ? 'bots.groups.pausedAll' : 'bots.groups.resumedAll'));
      onChanged?.();
    } catch (err) {
      setGroupNote(err instanceof Error ? err.message : 'action failed');
    } finally {
      setBusyAll(false);
    }
  }, [busyAll, members, onChanged, t]);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages.length, sending, scrollToBottom]);

  // Auto-grow the composer with its content, up to a cap, then scroll.
  const resizeComposer = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);
  useEffect(() => { resizeComposer(); }, [input, resizeComposer]);

  /**
   * One member bot answers in its OWN voice: a separate agent turn with that
   * bot's identity + instructions, streamed into its own message. Members never
   * share or merge a reply.
   */
  const runMember = useCallback(
    async (bot: AutomationView, text: string, prior: GroupMessage[], controllers: AbortController[]) => {
      const replyId = newId();
      append(group.id, {
        id: replyId, role: 'assistant', content: '', at: new Date().toISOString(),
        authorId: bot.id, authorName: bot.name,
      });
      const persona =
        `You are "${bot.name}", one member of the group chat "${group.name}". ` +
        `Your role: ${bot.description || '—'}. Your standing instructions: ${bot.action.objective || '—'}. ` +
        `Reply ONLY as ${bot.name}, in your own distinct voice. Do not speak for other ` +
        `members and do not summarize the room. Use your tools when asked.`;
      const history = [
        { role: 'user' as const, content: persona },
        { role: 'assistant' as const, content: `Understood — I am ${bot.name}.` },
        ...prior
          .filter((m) => !m.error && m.content.trim().length > 0)
          .slice(-8)
          .map((m) => ({
            role: m.role,
            // Prior room replies are labelled with their author so each bot can
            // tell who said what, without blending them into one voice.
            content: m.role === 'assistant' && m.authorName ? `${m.authorName}: ${m.content}` : m.content,
          })),
      ];
      const controller = new AbortController();
      controllers.push(controller);
      let streamed = '';
      try {
        const reply = await getAgentProvider().chat(
          [...history, { role: 'user' as const, content: text }],
          undefined,
          {
            chatId: `group-${group.id}-${bot.id}`,
            signal: controller.signal,
            onDelta: (chunk) => {
              streamed += chunk;
              updateMessage(group.id, replyId, { content: streamed });
            },
          },
        );
        const final = reply || streamed;
        updateMessage(
          group.id,
          replyId,
          final ? { content: final } : { content: `${bot.name} did not return a reply.`, error: true },
        );
      } catch (err) {
        if (controller.signal.aborted) {
          updateMessage(group.id, replyId, streamed ? { content: streamed } : { content: '(stopped)', error: true });
        } else {
          updateMessage(group.id, replyId, {
            content: err instanceof Error ? err.message : 'network error', error: true,
          });
        }
      }
    },
    [append, updateMessage, group.id, group.name],
  );

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending || members.length === 0) return;
    const prior = useBotGroupsStore.getState().byGroup[group.id] ?? [];
    append(group.id, { id: newId(), role: 'user', content: text, at: new Date().toISOString() });
    setInput('');
    setSending(true);
    const targets = audience === 'all' ? members : members.filter((b) => b.id === audience);
    const controllers: AbortController[] = [];
    controllersRef.current = controllers;
    try {
      // All targeted bots answer independently and in parallel; each streams
      // into its own message so no reply is combined.
      await Promise.all(targets.map((bot) => runMember(bot, text, prior, controllers)));
    } finally {
      controllersRef.current = [];
      setSending(false);
    }
  }, [input, sending, members, audience, append, group.id, runMember]);

  /** Stop every in-flight member reply, keeping whatever streamed so far. */
  const stop = useCallback(() => {
    controllersRef.current.forEach((c) => c.abort());
  }, []);

  return (
    <div className="glass-card flex h-full min-h-0 flex-col rounded-2xl">
      {/* Header — group identity + members */}
      <div className="flex items-start gap-3 border-b border-border/10 p-4">
        {group.image ? (
          <img src={group.image} alt="" className="h-12 w-12 shrink-0 rounded-2xl object-cover" />
        ) : (
          <GhostAvatar spec={groupSpec} size={48} />
        )}
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold">{group.name}</h2>
          <div className="mt-1 flex items-center gap-2">
            <div className="flex -space-x-1.5">
              {members.slice(0, 6).map((b) => (
                <BotAvatar
                  key={b.id}
                  botId={b.id}
                  spec={avatarFor(avatars, b.id)}
                  size={22}
                  className="rounded-full ring-2 ring-background"
                  title={b.name}
                />
              ))}
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <Users size={12} /> {t('bots.groups.members', { count: group.memberIds.length })}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          <Button size="sm" disabled={busyAll || members.length === 0} onClick={() => void runAll()}>
            {busyAll ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} {t('bots.runNow')}
          </Button>
          {allActive ? (
            <Button
              size="icon-sm"
              variant="outline"
              disabled={busyAll}
              title={t('bots.groups.pauseAll')}
              aria-label={t('bots.groups.pauseAll')}
              onClick={() => void setAllPausedState(true)}
            >
              <Pause size={14} />
            </Button>
          ) : (
            <Button
              size="icon-sm"
              variant="outline"
              disabled={busyAll}
              title={t('bots.groups.resumeAll')}
              aria-label={t('bots.groups.resumeAll')}
              onClick={() => void setAllPausedState(false)}
            >
              <Play size={14} />
            </Button>
          )}
          <Button
            size="icon-sm"
            variant="ghost"
            title={t('bots.jobsPanel.open')}
            aria-label={t('bots.jobsPanel.open')}
            aria-pressed={schedulerOpen}
            onClick={toggleScheduler}
            className={schedulerOpen ? 'bg-white/[0.08] text-primary' : ''}
          >
            <CalendarDays size={14} />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            title={t('bots.groups.settings')}
            aria-label={t('bots.groups.settings')}
            onClick={() => setSettingsOpen(true)}
          >
            <Settings size={14} />
          </Button>
          {confirmDelete ? (
            <>
              <Button size="sm" variant="destructive" onClick={() => { deleteGroup(group.id); onDeleted(group.id); }}>
                {t('bots.groups.delete')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
                {t('bots.groups.cancel')}
              </Button>
            </>
          ) : (
            <Button
              size="icon-sm"
              variant="ghost"
              title={t('bots.groups.delete')}
              aria-label={t('bots.groups.delete')}
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 size={14} />
            </Button>
          )}
        </div>
      </div>

      {/* Thread */}
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5">
        {messages.length === 0 && (
          <div className="mx-auto max-w-md py-8 text-center">
            {group.image ? (
              <img src={group.image} alt="" className="mx-auto h-16 w-16 rounded-2xl object-cover" />
            ) : (
              <GhostAvatar spec={groupSpec} size={64} className="mx-auto" />
            )}
            <p className="mt-3 text-sm font-medium">{group.name}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {t('bots.groups.dialogHint')}
            </p>
          </div>
        )}

        {groupNote && (
          <div className="glass-card-subtle mx-auto w-fit rounded-full px-3 py-1 text-[11px] text-muted-foreground">
            {groupNote}
          </div>
        )}

        {messages.map((m) =>
          !m.error && m.role === 'assistant' && !m.content ? null : (
            <GroupBubble key={m.id} message={m} groupName={group.name} groupSpec={groupSpec} groupImage={group.image} />
          ),
        )}

        {sending && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 size={14} className="animate-spin" />
            {t('bots.groups.answering')}
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-border/10 p-3">
        <div className="mb-2 flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded-full border border-border/50 px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:border-border hover:text-foreground"
                  title={t('bots.groups.audience')}
                  aria-label={t('bots.groups.audience')}
                />
              }
            >
              <Users size={12} />
              <span>
                {audience === 'all'
                  ? t('bots.groups.everyone')
                  : members.find((b) => b.id === audience)?.name ?? t('bots.groups.everyone')}
              </span>
              <ChevronDown size={12} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-52">
              <DropdownMenuItem onClick={() => setAudience('all')} className="gap-2">
                <Users size={14} /> <span className="flex-1">{t('bots.groups.everyone')}</span>
              </DropdownMenuItem>
              {members.map((b) => (
                <DropdownMenuItem key={b.id} onClick={() => setAudience(b.id)} className="gap-2">
                  <BotAvatar botId={b.id} spec={avatarFor(avatars, b.id)} size={16} title={b.name} />
                  <span className="flex-1 truncate">{b.name}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <span className="truncate text-[10px] text-muted-foreground">{t('bots.groups.audienceHint')}</span>
        </div>
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); }
            }}
            rows={1}
            placeholder={t('bots.groups.composer')}
            aria-label={t('bots.groups.composer')}
            className="max-h-[200px] min-h-10 flex-1 resize-none overflow-y-auto rounded-xl border border-input bg-transparent px-3 py-2 text-sm outline-none dark:bg-input/30"
          />
          {sending ? (
            <Button size="icon" variant="outline" onClick={stop} title={t('bots.groups.stop')} aria-label={t('bots.groups.stop')}>
              <Pause size={15} />
            </Button>
          ) : (
            <Button size="icon" onClick={() => void send()} disabled={!input.trim()} aria-label={t('bots.groups.composer')}>
              <ArrowUp size={15} />
            </Button>
          )}
        </div>
        <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
          <span className="truncate">{t('bots.groups.membersTitle')}: {members.map((m) => m.name).join(', ') || '—'}</span>
          {messages.length > 0 && (
            <button type="button" onClick={() => clearMessages(group.id)} className="shrink-0 hover:text-foreground">
              {t('bots.groups.clear')}
            </button>
          )}
        </div>
      </div>

      <GroupSettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} group={group} bots={bots} />
    </div>
  );
}

function GroupBubble({
  message,
  groupName,
  groupSpec,
  groupImage,
}: {
  message: GroupMessage;
  groupName: string;
  groupSpec: import('@/lib/bots/ghost').GhostSpec;
  groupImage?: string;
}) {
  const t = useT();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  // Each reply is from a specific member now, so show ITS avatar; fall back to
  // the room identity for older/user turns.
  const avatar = message.authorId
    ? <BotAvatar botId={message.authorId} spec={avatarFor(avatars, message.authorId)} size={28} className="mt-0.5 shrink-0" title={message.authorName} />
    : groupImage
      ? <img src={groupImage} alt="" className="mt-0.5 h-7 w-7 shrink-0 rounded-full object-cover" />
      : <GhostAvatar spec={groupSpec} size={28} className="mt-0.5 shrink-0" />;
  const copy = () => {
    if (typeof navigator === 'undefined' || !navigator.clipboard) return;
    void navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => { /* clipboard unavailable */ });
  };
  const timeRow = (
    <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
      <span>{formatDateTime(message.at)}</span>
      <button
        type="button"
        onClick={copy}
        className="flex h-5 w-5 cursor-pointer items-center justify-center rounded-md hover:bg-white/10 hover:text-foreground"
        title={copied ? t('bots.chat.copied') : t('bots.chat.copy')}
        aria-label={t('bots.chat.copy')}
      >
        {copied ? <CheckCircle2 size={12} /> : <Copy size={12} />}
      </button>
    </div>
  );
  // A room reply reads as a full-width document with no glass surface; only the
  // user's own turns (and honest error turns) are framed as bubbles.
  if (!isUser && !message.error) {
    return (
      <div className="group flex gap-2.5">
        {avatar}
        <div className="min-w-0 flex-1">
          <div className="mb-0.5 text-[10px] font-semibold text-muted-foreground">{message.authorName ?? groupName}</div>
          <Markdown content={message.content} compact className="w-full" />
          {timeRow}
        </div>
      </div>
    );
  }
  return (
    <div className={cn('group flex gap-2.5', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {!isUser && avatar}
      <div className={cn('flex min-w-0 max-w-[80%] flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'rounded-2xl px-3.5 py-2 text-sm',
            isUser
              ? 'bg-white/[0.08] text-foreground'
              : 'border border-rose-500/30 bg-rose-500/5 text-rose-200',
          )}
        >
          {!isUser && <div className="mb-0.5 text-[10px] font-semibold text-muted-foreground">{message.authorName ?? groupName}</div>}
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        </div>
        {timeRow}
      </div>
    </div>
  );
}
