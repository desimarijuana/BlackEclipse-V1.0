'use client';

// ── Fork + quote actions for the ChatBot shell ───────────────────────────────
//
// The shell is at its size ratchet, so the orchestration lives here instead:
// forking a conversation (clone + session copy + activation) and holding the
// pending quoted passage. The pure clone rules are in `fork.ts`; this hook only
// touches the shell's conversation store through the callbacks it is given.

import { useCallback, useRef, useState } from 'react';
import type { Conversation } from './chat-organization';
import type { Message, MessageQuote } from '@/types/chat';
import { forkConversation as buildFork, newChatId } from './fork';
import { cloneSessionContext } from './session-client';
import { useWorkspaceStore } from '../agent-workspace/store';
import { restoreWorkspaceForChat } from '../agent-workspace/restore';

export interface ChatConversationActionsOptions {
  conversationsRef: { current: Conversation[] };
  activeConversationIdRef: { current: string | null };
  /** The shell's conversation-store writer (cache + React state). */
  save: (updated: Conversation[]) => void;
  setActiveConversationId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  isBusy: () => boolean;
  /** Number of queued prompts that belong to the source chat. */
  queueSize: () => number;
  /** Called after the fork's session folder has been copied. */
  onSessionCloned?: () => void;
}

export interface ChatConversationActions {
  /** A selected passage waiting for the next send (null when none). */
  pendingQuote: MessageQuote | null;
  clearQuote: () => void;
  /** Put a quoted passage in the composer and focus it. */
  acceptQuote: (quote: MessageQuote) => void;
  /** Copy a conversation into a real new chat. */
  forkConversation: (sourceId: string, messageId?: string) => Promise<void>;
  /** Fork the ACTIVE conversation through one message. */
  forkFromMessage: (messageId: string) => void;
}

export function useChatConversationActions(
  options: ChatConversationActionsOptions,
): ChatConversationActions {
  const [pendingQuote, setPendingQuote] = useState<MessageQuote | null>(null);
  // Async handlers read the latest callbacks after an await.
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const clearQuote = useCallback(() => setPendingQuote(null), []);

  const acceptQuote = useCallback((quote: MessageQuote) => {
    setPendingQuote(quote);
    requestAnimationFrame(() => window.dispatchEvent(new CustomEvent('be:focus-chat')));
  }, []);

  const forkConversation = useCallback(async (sourceId: string, messageId?: string) => {
    const {
      conversationsRef,
      activeConversationIdRef,
      save,
      setActiveConversationId,
      setMessages,
      isBusy,
      queueSize,
      onSessionCloned,
    } = optionsRef.current;
    // A fork during a run/queue would copy partial state or run the source's
    // queued prompts in the new chat. Wait for a settled conversation.
    if (isBusy() || queueSize() > 0) return;
    const source = conversationsRef.current.find((c) => c.id === sourceId);
    if (!source || source.messages.length === 0) return;

    const fork = buildFork(source, { messageId, newChatId: () => newChatId() });
    save([fork, ...conversationsRef.current]);
    activeConversationIdRef.current = fork.id;
    setActiveConversationId(fork.id);
    setMessages(fork.messages);
    setPendingQuote(null);
    useWorkspaceStore.getState().clear();
    void restoreWorkspaceForChat(fork.messages, fork.id);

    // The transcript mirror handles the new conversation automatically; the
    // session folder needs an explicit context-file copy so attachments open.
    try {
      await cloneSessionContext(source.id, fork.id);
      onSessionCloned?.();
    } catch (err) {
      // Do not pretend the copy succeeded; the fork remains usable without it.
      console.warn('Fork created, but session files could not be copied:', err);
    }
  }, []);

  const forkFromMessage = useCallback((messageId: string) => {
    const activeId = optionsRef.current.activeConversationIdRef.current;
    if (!activeId) return;
    void forkConversation(activeId, messageId);
  }, [forkConversation]);

  return { pendingQuote, clearQuote, acceptQuote, forkConversation, forkFromMessage };
}
