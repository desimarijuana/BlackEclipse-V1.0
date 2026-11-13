'use client';

// ── Transcript message actions for the ChatBot shell ─────────────────────────
//
// Feedback, retry, edit/branch and redirect are pure transcript mutations. They
// live here so the at-ratchet shell stays small; the shell still owns the store
// and supplies its writers through callbacks.

import { useCallback, useRef } from 'react';
import type { Conversation } from './chat-organization';
import type { Message, ShellRun } from '@/types/chat';
import { turnTextForHarness } from './quote';
import { buildShellFailureTurn, buildShellTurn } from './shell';

export interface ChatMessageActionsOptions {
  conversationsRef: { current: Conversation[] };
  activeConversationIdRef: { current: string | null };
  save: (updated: Conversation[]) => void;
  setMessages: (messages: Message[]) => void;
  /** Append a user message and return the chat id it landed in. */
  addUserMessage: (message: Message) => string;
  /** Run a turn through the same send path as a composer submit. */
  dispatch: (chatId: string, userText: string, userMessage: Message) => Promise<void>;
}

export interface ChatMessageActions {
  feedback: (id: string, feedback: 'up' | 'down') => void;
  retry: (assistantId: string) => void;
  edit: (id: string, content: string) => void;
  resend: (id: string) => void;
  /**
   * Run one `!` shell command in the session workspace and append it to the
   * conversation as its own turn. It never dispatches an agent run: the run is
   * surfaced in the transcript, and the NEXT turn carries it as context.
   */
  runShell: (command: string) => Promise<void>;
}

export function useChatMessageActions(options: ChatMessageActionsOptions): ChatMessageActions {
  const optionsRef = useRef(options);
  optionsRef.current = options;

  /** Record a user's rating on an assistant turn. */
  const feedback = useCallback((id: string, value: 'up' | 'down') => {
    const { conversationsRef, activeConversationIdRef, save, setMessages } = optionsRef.current;
    const chatId = activeConversationIdRef.current;
    if (!chatId) return;
    const updated = conversationsRef.current.map((conversation) => {
      if (conversation.id !== chatId) return conversation;
      return {
        ...conversation,
        messages: conversation.messages.map((message) =>
          message.id === id
            ? { ...message, feedback: message.feedback === value ? undefined : value }
            : message,
        ),
      };
    });
    save(updated);
    const chat = updated.find((conversation) => conversation.id === chatId);
    if (chat) setMessages(chat.messages);
  }, []);

  /**
   * Edit a prompt: drop it and everything after it (a linear transcript means
   * later turns depended on it), then re-run the edited text. A quote on the
   * original turn is preserved.
   */
  const edit = useCallback((id: string, content: string) => {
    const { conversationsRef, activeConversationIdRef, save, setMessages, addUserMessage, dispatch } = optionsRef.current;
    const chatId = activeConversationIdRef.current;
    if (!chatId) return;
    const chat = conversationsRef.current.find((conversation) => conversation.id === chatId);
    if (!chat) return;
    const index = chat.messages.findIndex((message) => message.id === id);
    if (index === -1) return;

    const originalQuote = chat.messages[index].quote;
    const truncated = chat.messages.slice(0, index);
    const updated = conversationsRef.current.map((conversation) =>
      conversation.id === chatId
        ? { ...conversation, messages: truncated, timestamp: Date.now() }
        : conversation,
    );
    conversationsRef.current = updated;
    save(updated);
    if (activeConversationIdRef.current === chatId) setMessages(truncated);

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      ...(originalQuote ? { quote: originalQuote } : {}),
    };
    const newChatId = addUserMessage(userMessage);
    void dispatch(newChatId, turnTextForHarness(userMessage), userMessage);
  }, []);

  /** Re-run the prompt that produced an assistant turn (Retry/Regenerate). */
  const retry = useCallback((assistantId: string) => {
    const { conversationsRef, activeConversationIdRef } = optionsRef.current;
    const chatId = activeConversationIdRef.current;
    if (!chatId) return;
    const chat = conversationsRef.current.find((conversation) => conversation.id === chatId);
    if (!chat) return;
    const index = chat.messages.findIndex((message) => message.id === assistantId);
    if (index < 1) return;
    for (let i = index - 1; i >= 0; i -= 1) {
      if (chat.messages[i].role === 'user') {
        edit(chat.messages[i].id, chat.messages[i].content);
        return;
      }
    }
  }, [edit]);

  /** Re-send a user prompt unchanged (the Redirect action). */
  const resend = useCallback((id: string) => {
    const { conversationsRef, activeConversationIdRef } = optionsRef.current;
    const chat = conversationsRef.current.find(
      (conversation) => conversation.id === activeConversationIdRef.current,
    );
    const message = chat?.messages.find((candidate) => candidate.id === id);
    if (message && message.role === 'user') edit(id, message.content);
  }, [edit]);

  /**
   * `!` shell mode: run the command through the runtime's confined shell and
   * keep the run in the transcript. A refused/failed START is recorded as an
   * explicit unavailable turn — never as a successful empty run.
   */
  const runShell = useCallback(async (rawCommand: string) => {
    const { addUserMessage } = optionsRef.current;
    const command = rawCommand.trim();
    if (!command) return;
    try {
      const res = await fetch('/api/code/shell', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ command }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        result?: ShellRun;
        error?: string;
      };
      if (!res.ok || !data.result) {
        throw new Error(data.error ?? `Shell run failed (${res.status})`);
      }
      addUserMessage(buildShellTurn(command, data.result));
    } catch (err) {
      addUserMessage(
        buildShellFailureTurn(command, err instanceof Error ? err.message : 'Shell run failed'),
      );
    }
  }, []);

  return { feedback, retry, edit, resend, runShell };
}
