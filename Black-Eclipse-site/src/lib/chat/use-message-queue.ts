'use client';

// ── useMessageQueue — durable queue backed by localStorage ───────────────────
// The list rules live in `message-queue.ts`; persistence/cross-tab coordination
// lives in `queue-store.ts`. The hook keeps a React snapshot of every queued
// prompt and forwards edits. `items` spans all conversations; the shell filters
// what it renders.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MessageQuote } from '@/types/chat';
import {
  allQueued,
  clearStored,
  enqueueStored,
  isQueuePaused,
  moveStored,
  promoteStored,
  queuedFor,
  removeStored,
  setQueuePaused,
  subscribeQueueStore,
  updateStored,
} from './queue-store';
import { MAX_QUEUED_PROMPTS, type QueuedPrompt } from './message-queue';

export interface MessageQueue {
  items: QueuedPrompt[];
  /** Queued count per conversation, for sidebar badges. */
  counts: Record<string, number>;
  /** Resolves to false when the text was empty or the queue is full. */
  enqueue: (text: string, quote?: MessageQuote, chatId?: string | null) => boolean;
  remove: (id: string) => void;
  update: (id: string, text: string) => void;
  move: (id: string, direction: 'up' | 'down') => void;
  promote: (id: string) => void;
  /** Clear the whole queue, or only one conversation's prompts. */
  clear: (chatId?: string | null) => void;
  /** Current queue length, safe to read inside async handlers. */
  size: () => number;
  /** Queue length for one conversation (undefined = all). */
  sizeFor: (chatId?: string | null) => number;
  /** First item, safe to read inside async handlers. */
  peek: () => QueuedPrompt | undefined;
  /** First item for one conversation. */
  peekFor: (chatId?: string | null) => QueuedPrompt | undefined;
  paused: (chatId?: string | null) => boolean;
  setPaused: (chatId: string, paused: boolean) => void;
}

export function useMessageQueue(chatId?: string | null): MessageQueue {
  const [items, setItems] = useState<QueuedPrompt[]>([]);
  const scopeRef = useRef<string | null>(chatId ?? null);
  scopeRef.current = chatId ?? null;

  const refresh = useCallback(() => {
    setItems(allQueued());
  }, []);

  useEffect(() => {
    refresh();
    return subscribeQueueStore(refresh);
  }, [refresh]);

  const findItem = useCallback(
    (id: string): { item: QueuedPrompt; chatId: string } | null => {
      for (const item of items) {
        if (item.id === id && item.chatId) return { item, chatId: item.chatId };
      }
      return null;
    },
    [items],
  );

  const enqueue = useCallback(
    (text: string, quote?: MessageQuote, target?: string | null): boolean => {
      const resolved = target ?? scopeRef.current ?? '__default__';
      if (!resolved) return false;
      const item = enqueueStored(resolved, text, quote);
      if (!item) return false;
      refresh();
      return true;
    },
    [refresh],
  );

  const remove = useCallback(
    (id: string) => {
      const found = findItem(id);
      if (!found) return;
      removeStored(found.chatId, id);
      refresh();
    },
    [findItem, refresh],
  );

  const update = useCallback(
    (id: string, text: string) => {
      const found = findItem(id);
      if (!found) return;
      updateStored(found.chatId, id, text);
      refresh();
    },
    [findItem, refresh],
  );

  const move = useCallback(
    (id: string, direction: 'up' | 'down') => {
      const found = findItem(id);
      if (!found) return;
      moveStored(found.chatId, id, direction);
      refresh();
    },
    [findItem, refresh],
  );

  const promote = useCallback(
    (id: string) => {
      const found = findItem(id);
      if (!found) return;
      promoteStored(found.chatId, id);
      refresh();
    },
    [findItem, refresh],
  );

  const clear = useCallback(
    (target?: string | null) => {
      clearStored(target);
      refresh();
    },
    [refresh],
  );

  const counts = useMemo(() => {
    const next: Record<string, number> = {};
    for (const item of items) {
      if (item.chatId) next[item.chatId] = (next[item.chatId] ?? 0) + 1;
    }
    return next;
  }, [items]);

  const size = useCallback(() => items.length, [items]);
  const sizeFor = useCallback(
    (target?: string | null) =>
      target === undefined
        ? allQueued().length
        : queuedFor(target).length,
    [],
  );
  const peek = useCallback(() => items[0], [items]);
  const peekFor = useCallback(
    (target?: string | null) => queuedFor(target)[0],
    [],
  );
  const paused = useCallback((target?: string | null) => isQueuePaused(target), []);
  const setPaused = useCallback(
    (target: string, value: boolean) => {
      setQueuePaused(target, value);
      refresh();
    },
    [refresh],
  );

  return {
    items,
    counts,
    enqueue,
    remove,
    update,
    move,
    promote,
    clear,
    size,
    sizeFor,
    peek,
    peekFor,
    paused,
    setPaused,
  };
}

export { MAX_QUEUED_PROMPTS };
