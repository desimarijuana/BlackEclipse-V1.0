'use client';

// ── Group chat room ───────────────────────────────────────────────────────────
// A conversation shared by 2–6 bots. The user speaks to the room; the reply comes
// from the real harness with the room's member roster as standing context, and is
// attributed to the room (never to a specific bot, which we cannot guarantee).

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { ArrowUp, Loader2, Trash2, Users } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import {
  useBotGroupsStore, useHydrateBotGroups, type BotGroup, type GroupMessage,
} from '@/lib/bots/groups-store';
import { ghostSpecFromId } from '@/lib/bots/ghost';
import { formatDateTime } from '@/lib/bots/state';
import type { AutomationView } from '@/lib/harness/automation-browser';

export interface GroupChatRoomProps {
  group: BotGroup;
  bots: AutomationView[];
  onDeleted: (id: string) => void;
}

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

const NO_MESSAGES: GroupMessage[] = [];

export function GroupChatRoom({ group, bots, onDeleted }: GroupChatRoomProps) {
  const t = useT();
  useHydrateBotAvatars();
  useHydrateBotGroups();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const messages = useBotGroupsStore((s) => s.byGroup[group.id] ?? NO_MESSAGES);
  const append = useBotGroupsStore((s) => s.appendMessage);
  const clearMessages = useBotGroupsStore((s) => s.clearMessages);
  const deleteGroup = useBotGroupsStore((s) => s.deleteGroup);

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const members = useMemo(
    () => group.memberIds.map((id) => bots.find((b) => b.id === id)).filter((b): b is AutomationView => Boolean(b)),
    [group.memberIds, bots],
  );

  const groupSpec = useMemo(() => ghostSpecFromId(group.id), [group.id]);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages.length, sending, scrollToBottom]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    append(group.id, { id: newId(), role: 'user', content: text, at: new Date().toISOString() });
    setInput('');
    setSending(true);
    const roster = members.map((b) => `${b.name} (${b.description || 'no description'})`).join('; ');
    const persona =
      `You are the assistant for the group chat "${group.name}". ` +
      `Its members are: ${roster || 'no bots yet'}. ` +
      `Answer on behalf of the room, and use your tools to act when asked.`;
    const history = [
      { role: 'user' as const, content: persona },
      { role: 'assistant' as const, content: 'Understood — I am this room.' },
      ...messages.filter((m) => !m.error).slice(-10).map((m) => ({ role: m.role, content: m.content })),
    ];
    try {
      const res = await fetch('/api/harness/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text, history, chatId: `group-${group.id}` }),
      });
      const payload = (await res.json().catch(() => ({}))) as { content?: string; error?: string };
      if (!res.ok || !payload.content) {
        append(group.id, {
          id: newId(), role: 'assistant', at: new Date().toISOString(),
          content: payload.error ?? `The room could not respond (${res.status}).`, error: true,
          authorName: group.name,
        });
      } else {
        append(group.id, {
          id: newId(), role: 'assistant', content: payload.content, at: new Date().toISOString(),
          authorName: group.name,
        });
      }
    } catch (err) {
      append(group.id, {
        id: newId(), role: 'assistant', at: new Date().toISOString(),
        content: err instanceof Error ? err.message : 'network error', error: true, authorName: group.name,
      });
    } finally {
      setSending(false);
    }
  }, [input, sending, append, group.id, group.name, members, messages]);

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
        <div className="flex shrink-0 items-center gap-1.5">
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

        {messages.map((m) => (
          <GroupBubble key={m.id} message={m} groupName={group.name} groupSpec={groupSpec} groupImage={group.image} />
        ))}

        {sending && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 size={14} className="animate-spin" />
            {t('bots.groups.thinking', { name: group.name })}
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
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); }
            }}
            rows={1}
            placeholder={t('bots.groups.composer')}
            aria-label={t('bots.groups.composer')}
            className="max-h-40 min-h-10 flex-1 resize-none rounded-xl border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
          />
          <Button size="icon" onClick={() => void send()} disabled={sending || !input.trim()} aria-label={t('bots.groups.composer')}>
            <ArrowUp size={15} />
          </Button>
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted-foreground">
          <span>{t('bots.groups.membersTitle')}: {members.map((m) => m.name).join(', ') || '—'}</span>
          {messages.length > 0 && (
            <button type="button" onClick={() => clearMessages(group.id)} className="hover:text-foreground">
              {t('bots.groups.clear')}
            </button>
          )}
        </div>
      </div>
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
  const isUser = message.role === 'user';
  return (
    <div className={cn('flex gap-2.5', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {!isUser && (
        groupImage
          ? <img src={groupImage} alt="" className="mt-0.5 h-7 w-7 shrink-0 rounded-full object-cover" />
          : <GhostAvatar spec={groupSpec} size={28} className="mt-0.5 shrink-0" />
      )}
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
        {!isUser && <div className="mb-0.5 text-[10px] font-semibold text-muted-foreground">{message.authorName ?? groupName}</div>}
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
        <div className="mt-1 text-[10px] text-muted-foreground">{formatDateTime(message.at)}</div>
      </div>
    </div>
  );
}
