// ── Bot chat store ───────────────────────────────────────────────────────────
// Per-bot conversation threads, persisted client-side (the repo's convention for
// ephemeral chat UI state). Bots run real agent turns through
// `/api/harness/chat`; these messages are the visible thread for each bot.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';

export const BOT_CHAT_KEY = 'be_bot_chat_v1';

export interface BotMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  at: string;
  /** True when the assistant turn failed (shown as an honest error bubble). */
  error?: boolean;
}

interface BotChatStore {
  byBot: Record<string, BotMessage[]>;
  hydrated: boolean;
  hydrate: () => void;
  setMessages: (botId: string, messages: BotMessage[]) => void;
  append: (botId: string, message: BotMessage) => void;
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
