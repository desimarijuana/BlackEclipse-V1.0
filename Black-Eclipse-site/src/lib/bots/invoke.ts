// ── Bot / group-chat turn invoker (shared) ───────────────────────────────────
// The ONE place a bot-as-a-turn (or a group member-as-a-turn) is assembled and
// run. Lifted out of `bot-chat.tsx` and `group-chat-room.tsx` so the Bots
// workspace, the group rooms AND the main-chat `@` delegation all speak to the
// runtime exactly the same way — same persona, same history windowing, same
// private per-conversation memory scope and chat-id scheme. No second agent
// loop: this still goes through the one streaming agent provider.
//
// Callers own the transcript (their own store) and pass `onDelta`; this module
// never writes to a store.

'use client';

import { getAgentProvider } from '@/lib/agent/registry';
import type { ChatMessage } from '@/lib/agent/types';
import type { AutomationView } from '@/lib/harness/automation-client';
import type { BotGroup } from '@/lib/bots/groups-store';

/** Prior bot-chat turns. `error` marks a failed turn, excluded from context. */
export interface PriorBotTurn {
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
}

/** Prior group-room turns. `authorName` labels who spoke (member replies only). */
export interface PriorGroupTurn {
  role: 'user' | 'assistant';
  content: string;
  authorName?: string;
  error?: boolean;
}

/** The chat id whose PRIVATE per-conversation memory a bot's turns belong to. */
export function botChatId(botId: string): string {
  return `bot-${botId}`;
}

/** The chat id whose PRIVATE per-conversation memory a group member's turns belong to. */
export function groupMemberChatId(groupId: string, botId: string): string {
  return `group-${groupId}-${botId}`;
}

/** The standing identity/instructions line for a bot answering as itself. */
export function botPersona(bot: AutomationView): string {
  const instructions = bot.action.objective ?? bot.description ?? '';
  return (
    `You are the persistent bot "${bot.name}" (id: ${bot.id}). ` +
    `Purpose: ${bot.description || '—'}. Standing instructions: ${instructions || '—'}. ` +
    `Answer as this bot, and use your tools to act when the user asks.`
  );
}

/** The standing identity/instructions line for one member inside a group room. */
export function groupMemberPersona(group: BotGroup, bot: AutomationView): string {
  return (
    `You are "${bot.name}", one member of the group chat "${group.name}". ` +
    `Your role: ${bot.description || '—'}. Your standing instructions: ${bot.action.objective || '—'}. ` +
    `Reply ONLY as ${bot.name}, in your own distinct voice. Do not speak for other ` +
    `members and do not summarize the room. Use your tools when asked.`
  );
}

/** Build the message list for a bot-as-a-turn: persona, ack, then recent turns. */
export function buildBotMessages(
  bot: AutomationView,
  text: string,
  prior: readonly PriorBotTurn[],
  limit = 10,
): ChatMessage[] {
  const history: ChatMessage[] = [
    { role: 'user', content: botPersona(bot) },
    { role: 'assistant', content: 'Understood — I am this bot.' },
    ...prior
      .filter((m) => !m.error && m.content.trim().length > 0)
      .slice(-limit)
      .map((m) => ({ role: m.role, content: m.content })),
  ];
  return [...history, { role: 'user', content: text }];
}

/** Build the message list for one group member's turn (prior turns author-labelled). */
export function buildGroupMemberMessages(
  group: BotGroup,
  bot: AutomationView,
  text: string,
  prior: readonly PriorGroupTurn[],
  limit = 8,
): ChatMessage[] {
  const history: ChatMessage[] = [
    { role: 'user', content: groupMemberPersona(group, bot) },
    { role: 'assistant', content: `Understood — I am ${bot.name}.` },
    ...prior
      .filter((m) => !m.error && m.content.trim().length > 0)
      .slice(-limit)
      .map((m) => ({
        role: m.role,
        content: m.role === 'assistant' && m.authorName ? `${m.authorName}: ${m.content}` : m.content,
      })),
  ];
  return [...history, { role: 'user', content: text }];
}

export interface RunBotTurnArgs {
  bot: AutomationView;
  text: string;
  prior: readonly PriorBotTurn[];
  model?: string;
  signal?: AbortSignal;
  onDelta?: (chunk: string) => void;
}

/**
 * Run one turn as the bot and resolve its final reply text. The caller owns the
 * placeholder message and the transcript; it streams `onDelta` into it.
 */
export async function runBotTurn(args: RunBotTurnArgs): Promise<string> {
  const { bot, text, prior, model, signal, onDelta } = args;
  return getAgentProvider().chat(buildBotMessages(bot, text, prior), undefined, {
    chatId: botChatId(bot.id),
    memoryScope: 'conversation',
    model: model || undefined,
    signal,
    onDelta,
  });
}

export interface RunGroupMemberTurnArgs {
  group: BotGroup;
  bot: AutomationView;
  text: string;
  prior: readonly PriorGroupTurn[];
  model?: string;
  signal?: AbortSignal;
  onDelta?: (chunk: string) => void;
}

/**
 * Run one group member's turn and resolve its final reply. Members never share a
 * reply: each streams into its own message via `onDelta`.
 */
export async function runGroupMemberTurn(args: RunGroupMemberTurnArgs): Promise<string> {
  const { group, bot, text, prior, model, signal, onDelta } = args;
  return getAgentProvider().chat(buildGroupMemberMessages(group, bot, text, prior), undefined, {
    chatId: groupMemberChatId(group.id, bot.id),
    memoryScope: 'conversation',
    model: model || undefined,
    signal,
    onDelta,
  });
}
