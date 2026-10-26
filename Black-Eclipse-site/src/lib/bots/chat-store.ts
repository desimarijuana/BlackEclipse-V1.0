// ── Bot chat store ───────────────────────────────────────────────────────────
// Per-bot conversation threads, persisted client-side (the repo's convention for
// ephemeral chat UI state). Bots run real agent turns through the streaming
// agent provider (`getAgentProvider`), so a long tool-heavy run is not bound by
// the one-shot front door's 180s request cap; these messages are the visible
// thread for each bot.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import type { DelegationView } from '@/lib/agent/response-model';

export const BOT_CHAT_KEY = 'be_bot_chat_v1';

export interface BotMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  at: string;
  /** True when the assistant turn failed (shown as an honest error bubble). */
  error?: boolean;
  /** Optional thumbs feedback on an assistant turn. */
  feedback?: 'up' | 'down';
  /** True when this assistant turn came from an AUTONOMOUS run (schedule, event,
   *  condition or manual "Run now") rather than the interactive composer. Such a
   *  turn is tagged in the thread and is not editable/regenerable. */
  scheduled?: boolean;
  /** The execution id that produced this turn — the idempotency key so an
   *  autonomous answer is appended exactly once (across polls and reloads). */
  runId?: string;
  /** Parallel fan-outs this bot ran, so the thread can show the live agent card. */
  delegations?: DelegationView[];
}

interface BotChatStore {
  byBot: Record<string, BotMessage[]>;
  hydrated: boolean;
  hydrate: () => void;
  setMessages: (botId: string, messages: BotMessage[]) => void;
  append: (botId: string, message: BotMessage) => void;
  /** Append an autonomous run's answer ONCE. Returns false when that execution
   *  is already in the thread (deduped by `runId`), true when it was added. */
  appendScheduled: (botId: string, message: BotMessage & { runId: string }) => boolean;
  /** Patch one message in place — used to fill the live streaming reply. A
   *  streaming caller passes `persist=false`; the terminal patch persists. */
  update: (botId: string, id: string, patch: Partial<BotMessage>, persist?: boolean) => void;
  clear: (botId: string) => void;
}

function persist(byBot: Record<string, BotMessage[]>) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(BOT_CHAT_KEY, JSON.stringify(byBot));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

function isMessage(v: unknown): v is BotMessage {
  if (!v || typeof v !== 'object') return false;
  const m = v as Record<string, unknown>;
  return (
    typeof m.id === 'string' &&
    (m.role === 'user' || m.role === 'assistant') &&
    typeof m.content === 'string'
  );
}

export const useBotChatStore = create<BotChatStore>((set, get) => ({
  byBot: {},
  hydrated: false,

  hydrate: () => {
    let byBot: Record<string, BotMessage[]> = {};
    if (typeof window !== 'undefined') {
      try {
        const raw = localStorage.getItem(BOT_CHAT_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as Record<string, unknown>;
          if (parsed && typeof parsed === 'object') {
            for (const [id, list] of Object.entries(parsed)) {
              if (Array.isArray(list)) byBot[id] = list.filter(isMessage);
            }
          }
        }
      } catch {
        byBot = {};
      }
    }
    set({ byBot, hydrated: true });
  },

  setMessages: (botId, messages) => {
    const byBot = { ...get().byBot, [botId]: messages };
    persist(byBot);
    set({ byBot });
  },

  append: (botId, message) => {
    const byBot = { ...get().byBot, [botId]: [...(get().byBot[botId] ?? []), message] };
    persist(byBot);
    set({ byBot });
  },

  appendScheduled: (botId, message) => {
    const list = get().byBot[botId] ?? [];
    // Idempotent by execution id: a re-poll (or a reload that re-syncs history)
    // must never double-post the same autonomous answer.
    if (message.runId && list.some((m) => m.runId === message.runId)) return false;
    const byBot = { ...get().byBot, [botId]: [...list, message] };
    persist(byBot);
    set({ byBot });
    return true;
  },

  update: (botId, id, patch, persistNow = true) => {
    const list = get().byBot[botId];
    if (!list) return;
    const byBot = { ...get().byBot, [botId]: list.map((m) => (m.id === id ? { ...m, ...patch } : m)) };
    if (persistNow) persist(byBot);
    set({ byBot });
  },

  clear: (botId) => {
    const next = { ...get().byBot };
    delete next[botId];
    persist(next);
    set({ byBot: next });
  },
}));

export function useHydrateBotChat() {
  const hydrate = useBotChatStore((s) => s.hydrate);
  const hydrated = useBotChatStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}
