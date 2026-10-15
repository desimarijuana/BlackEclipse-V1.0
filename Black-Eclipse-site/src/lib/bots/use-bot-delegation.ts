// ── Delegated `@mention` turns (main chat → a bot / group chat) ───────────────
// The main composer can `@`-mention a bot or a group room. This hook owns the
// whole surface for that: it hydrates the user's bots + group rooms into a
// mentionable list, then, for a mentioned turn, builds the context, expands a
// room into one turn per member, runs each through the shared invoker, and
// streams each reply into its own attributed message. It is the SAME runtime path
// the Bots workspace uses — no second agent loop, nothing fabricated.
//
// Two things keep a delegated turn faithful to a Bots-tab turn:
//   * the exchange is MIRRORED into the bot's/room's own thread (so the Bots tab
//     shows it), and
//   * a mid-run approval is surfaced on the message (the main chat's existing
//     ApprovalCard renders it) and can be decided here.
//
// Extracted from the SPA shell (`stock-chat.tsx`) to keep that file small; the
// host passes only the few transcript closures it already owns.

'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { Message } from '@/types/chat';
import type { HarnessUiEvent } from '@/lib/agent/events';
import type { AutomationView } from '@/lib/harness/automation-client';
import type { BotGroup } from '@/lib/bots/groups-store';
import { useBotGroupsStore, useHydrateBotGroups } from '@/lib/bots/groups-store';
import { useBotChatStore } from '@/lib/bots/chat-store';
import { useBotsStore } from '@/lib/bots/bots-store';
import { buildMentionTargets, type MentionTarget } from '@/lib/bots/mentions';
import {
  runBotTurn, runGroupMemberTurn,
  type PriorBotTurn, type PriorGroupTurn,
} from '@/lib/bots/invoke';
import { sound } from '@/lib/sounds';

export interface BotDelegationHost {
  /** The composer's model choice for this turn (optional). */
  model?: string;
  /** Current transcript of a conversation (read through the host's ref). */
  getMessages: (chatId: string) => Message[];
  /** Append an assistant message (host keeps its own store + persistence). */
  appendAssistantReply: (chatId: string, message: Message) => void;
  /** Replace an assistant message in place (streaming); `persist=false` skips I/O. */
  replaceAssistantReply: (chatId: string, id: string, message: Message, persist?: boolean) => void;
  /** Persist the transcript once a delegated batch settles. */
  persist: () => void;
  /** Toggle the host's busy flag (swaps the composer's submit for Stop). */
  setBusy: (busy: boolean) => void;
  /** Whether a turn is already in flight (host ref). */
  isInFlight: () => boolean;
  /** Set the host's in-flight guard. */
  setInFlight: (value: boolean) => void;
  /** Fallback when no mentioned target resolves — runs the normal agent. */
  runFallback: (chatId: string, userText: string) => void | Promise<void>;
}

export interface BotDelegation {
  /** Bots + group chats the composer can `@`-mention (from the live stores). */
  mentionTargets: MentionTarget[];
  /** Delegate `userText` to the mentioned bots/rooms. No-op while a turn is in flight. */
  run: (chatId: string, userText: string, targets: readonly MentionTarget[]) => Promise<void>;
  /** Abort every in-flight delegated turn. Returns true when something was aborted. */
  abort: () => boolean;
  /** Answer a pending approval raised by a delegated run. Resolves true on success. */
  decide: (approve: boolean, remember?: boolean) => Promise<boolean>;
}

/** Where a delegated run's blocking approval lives, so it can be decided. */
interface PendingRef {
  chatId: string;
  messageId: string;
}

export function useBotDelegation(host: BotDelegationHost): BotDelegation {
  // Read the host through a ref so `run` is stable and always sees fresh state.
  const hostRef = useRef(host);
  hostRef.current = host;
  const controllersRef = useRef<AbortController[]>([]);
  const pendingRef = useRef<PendingRef | null>(null);

  // The mentionable list: the live bots + group rooms. Hydrated once so the `@`
  // palette has real data everywhere the composer is reachable.
  const bots = useBotsStore((s) => s.bots);
  const hydrateBots = useBotsStore((s) => s.hydrate);
  const groups = useBotGroupsStore((s) => s.groups);
  useHydrateBotGroups();
  useEffect(() => { void hydrateBots(); }, [hydrateBots]);
  const mentionTargets = useMemo(() => buildMentionTargets(bots, groups), [bots, groups]);

  // Abort any in-flight stream if the surface unmounts so it is not orphaned.
  useEffect(() => () => { controllersRef.current.forEach((c) => c.abort()); }, []);

  const run = useCallback(async (chatId: string, userText: string, targets: readonly MentionTarget[]) => {
    const h = hostRef.current;
    if (h.isInFlight()) return;

    // Read the stores fresh (not a render snapshot) so a just-created bot/room
    // is resolvable at send time.
    const liveBots: readonly AutomationView[] = useBotsStore.getState().bots;
    const liveGroups: readonly BotGroup[] = useBotGroupsStore.getState().groups;

    // Context: the recent turns of THIS main conversation, so a delegation can
    // build on what the user and Eclipse just discussed. Bots additionally keep
    // their own private memory via the run's `bot-<id>` conversation scope.
    const prior = h.getMessages(chatId).filter((m) => m.role === 'user' || m.role === 'assistant');
    const priorBot: PriorBotTurn[] = prior.map((m) => ({ role: m.role, content: m.content, error: Boolean(m.error) }));
    const priorGroup: PriorGroupTurn[] = prior.map((m) => ({
      role: m.role, content: m.content, error: Boolean(m.error), authorName: m.author?.name,
    }));

    // Expand: a bot target is one turn; a room target is one turn per member.
    type Task = { bot: AutomationView; group?: BotGroup };
    const tasks: Task[] = [];
    for (const target of targets) {
      if (target.kind === 'bot') {
        const bot = liveBots.find((b) => b.id === target.id);
        if (bot) tasks.push({ bot });
      } else {
        const group = liveGroups.find((g) => g.id === target.id);
        if (!group) continue;
        for (const id of group.memberIds) {
          const bot = liveBots.find((b) => b.id === id);
          if (bot) tasks.push({ bot, group });
        }
      }
    }
    if (tasks.length === 0) {
      // Nothing resolvable (e.g. a room whose members were deleted) — fall back
      // to the normal agent so the message is never silently swallowed.
      await h.runFallback(chatId, userText);
      return;
    }

    h.setInFlight(true);
    h.setBusy(true);
    sound.tick();

    // A room's user turn is mirrored ONCE no matter how many members reply.
    const mirroredGroups = new Set<string>();
    const controllers: AbortController[] = [];
    controllersRef.current = controllers;

    const runOne = async (task: Task) => {
      const { bot } = task;
      const placeholderId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const startedAt = Date.now();
      const base: Message = {
        id: placeholderId,
        role: 'assistant',
        content: '',
        status: 'queued',
        author: { id: bot.id, kind: 'bot', name: bot.name },
      };
      h.appendAssistantReply(chatId, base);
      const controller = new AbortController();
      controllers.push(controller);
      let streamed = '';

      // A mid-run approval is surfaced on THIS message so the main chat's existing
      // ApprovalCard renders (it reads a message's `pendingApproval`); `pendingRef`
      // remembers where it lives so `decide()` can answer it.
      const onEvent = (ev: HarnessUiEvent) => {
        if (ev.kind === 'approval_request') {
          pendingRef.current = { chatId, messageId: placeholderId };
          h.replaceAssistantReply(chatId, placeholderId, {
            ...base, content: streamed, status: 'awaiting_approval', pendingApproval: ev.approval,
          }, false);
        } else if (ev.kind === 'approval_resolved') {
          if (pendingRef.current?.messageId === placeholderId) pendingRef.current = null;
          h.replaceAssistantReply(chatId, placeholderId, {
            ...base, content: streamed, status: 'streaming', pendingApproval: undefined,
          }, false);
        }
      };

      try {
        const onDelta = (chunk: string) => {
          streamed += chunk;
          h.replaceAssistantReply(chatId, placeholderId, { ...base, content: streamed, status: 'streaming' }, false);
        };
        const reply = task.group
          ? await runGroupMemberTurn({ group: task.group, bot, text: userText, prior: priorGroup, signal: controller.signal, onDelta, onEvent })
          : await runBotTurn({ bot, text: userText, prior: priorBot, model: h.model || undefined, signal: controller.signal, onDelta, onEvent });
        const final = reply || streamed;
        const durationMs = Math.max(0, Date.now() - startedAt);
        if (final) {
          h.replaceAssistantReply(chatId, placeholderId, { ...base, content: final, status: 'completed', durationMs });
          // Mirror the exchange into the bot's / room's own thread so the Bots tab
          // shows it (memory is already shared via the run's conversation scope).
          mirrorTurn(task, placeholderId, userText, final, mirroredGroups);
        } else {
          h.replaceAssistantReply(chatId, placeholderId, { ...base, content: `${bot.name} did not return a reply.`, status: 'error', error: { message: `${bot.name} did not return a reply.` }, durationMs });
        }
      } catch (err) {
        const durationMs = Math.max(0, Date.now() - startedAt);
        h.replaceAssistantReply(chatId, placeholderId, controller.signal.aborted
          ? { ...base, content: streamed, status: 'cancelled', durationMs }
          : { ...base, content: '', status: 'error', error: { message: err instanceof Error ? err.message : 'network error' }, durationMs });
      }
    };

    try {
      // Every mentioned target answers independently and in parallel; each streams
      // into its own message so no two replies are ever combined.
      await Promise.all(tasks.map(runOne));
      sound.message();
    } finally {
      controllersRef.current = [];
      pendingRef.current = null;
      h.setInFlight(false);
      h.setBusy(false);
      h.persist();
    }
  }, []);

  const abort = useCallback(() => {
    if (controllersRef.current.length === 0) return false;
    controllersRef.current.forEach((c) => c.abort());
    pendingRef.current = null;
    return true;
  }, []);

  const decide = useCallback(async (approve: boolean, remember = false): Promise<boolean> => {
    const p = pendingRef.current;
    if (!p) return false;
    const h = hostRef.current;
    const msg = h.getMessages(p.chatId).find((m) => m.id === p.messageId);
    const approval = msg?.pendingApproval;
    if (!approval) return false;
    // Clear the card optimistically; restore it if the decision POST fails so the
    // operator can retry (mirrors the main `useAgentRun.decide` contract).
    h.replaceAssistantReply(p.chatId, p.messageId, { ...(msg as Message), pendingApproval: undefined, status: 'streaming' }, true);
    pendingRef.current = null;
    try {
      const res = await fetch(
        `/api/harness/mcp/approvals/${encodeURIComponent(approval.id)}/decide`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ approve, remember: approve && remember }),
        },
      );
      if (!res.ok) throw new Error(`decision failed (${res.status})`);
      return true;
    } catch {
      h.replaceAssistantReply(p.chatId, p.messageId, { ...(msg as Message) }, true);
      pendingRef.current = p;
      return false;
    }
  }, []);

  return { mentionTargets, run, abort, decide };
}

/**
 * Append a completed delegated exchange to the bot's or room's own thread so the
 * Bots tab reflects it. A room's user turn is written once (guarded by `seen`).
 */
function mirrorTurn(
  task: { bot: AutomationView; group?: BotGroup },
  messageId: string,
  userText: string,
  final: string,
  seen: Set<string>,
): void {
  const at = new Date().toISOString();
  if (task.group) {
    const store = useBotGroupsStore.getState();
    if (!seen.has(task.group.id)) {
      seen.add(task.group.id);
      store.appendMessage(task.group.id, { id: `${messageId}-u`, role: 'user', content: userText, at });
    }
    store.appendMessage(task.group.id, {
      id: messageId, role: 'assistant', content: final, at,
      authorId: task.bot.id, authorName: task.bot.name,
    });
  } else {
    const store = useBotChatStore.getState();
    store.append(task.bot.id, { id: `${messageId}-u`, role: 'user', content: userText, at });
    store.append(task.bot.id, { id: messageId, role: 'assistant', content: final, at });
  }
}
