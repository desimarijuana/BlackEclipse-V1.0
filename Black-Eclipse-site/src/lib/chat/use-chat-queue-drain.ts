'use client';

// ── Per-conversation queue drain ─────────────────────────────────────────────
// A queued prompt belongs to the conversation that queued it. The drain picks
// the first prompt whose OWN conversation is idle, so a queue in chat A keeps
// moving while the user watches chat B. Extracted from the at-ratchet chat shell.

import { useEffect, useRef } from 'react';
import type { Message } from '@/types/chat';
import { runManager } from '@/lib/agent/run-manager';
import type { MessageQueue } from './use-message-queue';
import { takeNextFor } from './queue-store';
import { turnTextForHarness } from './quote';

export interface ChatQueueDrainOptions {
  messageQueue: MessageQueue;
  addMessageToChat: (targetId: string | null, message: Message) => string;
  dispatchTurn: (chatId: string, userText: string, message: Message) => Promise<void>;
  /** True when a delegated (@-mentioned) turn owns the runtime slot. */
  blocked: () => boolean;
  /** False while the persisted transcript list is still hydrating. */
  conversationExists?: (chatId: string) => boolean;
  /** Re-run the drain when this changes (run start/finish or queue contents). */
  revision: unknown;
}

export function useChatQueueDrain(options: ChatQueueDrainOptions) {
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const drainingRef = useRef(false);
  const drainRef = useRef<() => void>(() => undefined);

  const runDrain = async (): Promise<void> => {
    const o = optionsRef.current;
    if (drainingRef.current || o.blocked()) return;
    const next = o.messageQueue.items.find(
      (item) =>
        !runManager.isBusy(item.chatId ?? null) &&
        !o.messageQueue.paused(item.chatId) &&
        // A persisted prompt for a chat whose transcript has not hydrated yet
        // must wait; otherwise boot resume would create a duplicate chat.
        (!item.chatId || !o.conversationExists || o.conversationExists(item.chatId)),
    );
    if (!next) return;
    drainingRef.current = true;
    // Atomic across tabs: exactly one tab takes this prompt.
    const taken = await takeNextFor(next.chatId ?? '__default__');
    if (!taken) {
      drainingRef.current = false;
      return; // another tab took it; the store subscription re-runs us
    }
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: taken.text,
      ...(taken.quote ? { quote: taken.quote } : {}),
    };
    const chatId = o.addMessageToChat(taken.chatId ?? null, userMsg);
    void o
      .dispatchTurn(chatId, turnTextForHarness(userMsg), userMsg)
      .finally(() => {
        drainingRef.current = false;
        drainRef.current();
      });
  };

  drainRef.current = () => {
    void runDrain();
  };

  useEffect(() => {
    drainRef.current();
  }, [options.messageQueue.items, options.revision]);

  return drainRef;
}
