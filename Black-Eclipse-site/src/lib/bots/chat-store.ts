// ── Bot chat store ───────────────────────────────────────────────────────────
// Per-bot conversation threads. localStorage gives an instant, offline-first
// render; the document is also mirrored to the server (`BotState`, key `chat`)
// so clearing browser storage or opening a second tab does not erase the
// threads. The newest client timestamp wins. Bots run real agent turns through
// the streaming agent provider (`getAgentProvider`), so a long tool-heavy run is
// not bound by the one-shot front door's 180s request cap.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import type { DelegationView, PendingApproval, PendingClarification } from '@/lib/agent/response-model';
import {
  newBotStateEnvelope,
  pullBotState,
  queueBotStatePush,
  readLocalEnvelope,
  shouldAdoptRemote,
  shouldPushLocal,
  writeLocalEnvelope,
  type BotStateEnvelope,
} from '@/lib/bots/state-sync';

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
  /** A blocking permission decision raised by this turn. Rendered by the bot
   *  thread so an approval-gated tool can finish here, exactly as in main chat. */
  pendingApproval?: PendingApproval;
  /** A paused `clarify` question from this turn. */
  pendingClarification?: PendingClarification;
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

/** Persist locally and queue the server mirror (best effort). */
function persist(
  byBot: Record<string, BotMessage[]>,
  envelope?: BotStateEnvelope<Record<string, BotMessage[]>>,
) {
  const next = envelope ?? newBotStateEnvelope(byBot);
  writeLocalEnvelope(BOT_CHAT_KEY, next);
  queueBotStatePush('chat', next);
}

/** Validate a decoded document from either storage medium. */
function sanitizeByBot(input: unknown): Record<string, BotMessage[]> {
  const byBot: Record<string, BotMessage[]> = {};
  if (input && typeof input === 'object') {
    for (const [id, list] of Object.entries(input as Record<string, unknown>)) {
      if (Array.isArray(list)) byBot[id] = list.filter(isMessage);
    }
  }
  return byBot;
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

export const useBotChatStore = create<BotChatStore>((set, get) => {
  /** Reconcile with the durable mirror without blocking the local render. */
  const syncFromServer = async () => {
    const remote = await pullBotState('chat');
    const local = readLocalEnvelope<Record<string, BotMessage[]>>(BOT_CHAT_KEY);
    if (!remote) {
      if (local) queueBotStatePush('chat', local);
      return;
    }
    if (shouldAdoptRemote(local?.updatedAt, remote.updatedAt)) {
      try {
        const data = sanitizeByBot(JSON.parse(remote.document) as unknown);
        writeLocalEnvelope(BOT_CHAT_KEY, newBotStateEnvelope(data, new Date(remote.updatedAt)));
        set({ byBot: data });
      } catch {
        /* malformed mirror — keep the local copy */
      }
      return;
    }
    if (local && shouldPushLocal(local.updatedAt, remote.updatedAt)) {
      queueBotStatePush('chat', local);
    }
  };

  return {
    byBot: {},
    hydrated: false,

    hydrate: () => {
      const local = readLocalEnvelope<Record<string, BotMessage[]>>(BOT_CHAT_KEY);
      set({ byBot: sanitizeByBot(local?.data), hydrated: true });
      void syncFromServer();
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
  };
});

export function useHydrateBotChat() {
  const hydrate = useBotChatStore((s) => s.hydrate);
  const hydrated = useBotChatStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
  // Adopt a newer document written by another tab.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === BOT_CHAT_KEY) hydrate();
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [hydrate]);
}
