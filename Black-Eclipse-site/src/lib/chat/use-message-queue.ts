'use client';

// ── useMessageQueue — the queue's React home ─────────────────────────────────
// The pure list rules live in `message-queue.ts`; this hook keeps a ref in
// lockstep with state so an async drain loop reads the latest queue immediately
// after a mutation (React state alone would be one render behind).

import { useCallback, useRef, useState } from 'react';
import type { MessageQuote } from '@/types/chat';
import {
  MAX_QUEUED_PROMPTS,
  enqueuePrompt,
  moveQueued,
  promoteQueued,
  removeQueued,
  updateQueued,
  type QueuedPrompt,
} from './message-queue';

function newId(): string {
  return `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

export interface MessageQueue {
  items: QueuedPrompt[];
  /** Resolves to false when the text was empty or the queue is full. */
  enqueue: (text: string, quote?: MessageQuote) => boolean;
  remove: (id: string) => void;
  update: (id: string, text: string) => void;
  move: (id: string, direction: 'up' | 'down') => void;
  promote: (id: string) => void;
  clear: () => void;
  /** Current queue length, safe to read inside async handlers. */
  size: () => number;
  /** First item, safe to read inside async handlers. */
  peek: () => QueuedPrompt | undefined;
}

export function useMessageQueue(): MessageQueue {
  const [items, setItems] = useState<QueuedPrompt[]>([]);
  const itemsRef = useRef<QueuedPrompt[]>(items);
  itemsRef.current = items;

  const commit = useCallback((next: readonly QueuedPrompt[]): boolean => {
    if (next === itemsRef.current) return false;
    itemsRef.current = [...next];
    setItems(itemsRef.current);
    return true;
  }, []);

  const enqueue = useCallback(
    (text: string, quote?: MessageQuote): boolean => {
      const next = enqueuePrompt(itemsRef.current, text, newId, Date.now(), quote);
      return commit(next);
    },
    [commit],
  );

  const remove = useCallback(
    (id: string) => {
      commit(removeQueued(itemsRef.current, id));
    },
    [commit],
  );

  const update = useCallback(
    (id: string, text: string) => {
      commit(updateQueued(itemsRef.current, id, text));
    },
    [commit],
  );

  const move = useCallback(
    (id: string, direction: 'up' | 'down') => {
      commit(moveQueued(itemsRef.current, id, direction));
    },
    [commit],
  );

  const promote = useCallback(
    (id: string) => {
      commit(promoteQueued(itemsRef.current, id));
    },
    [commit],
  );

  const clear = useCallback(() => {
    commit([]);
  }, [commit]);

  const size = useCallback(() => itemsRef.current.length, []);
  const peek = useCallback(() => itemsRef.current[0], []);

  return { items, enqueue, remove, update, move, promote, clear, size, peek };
}

export { MAX_QUEUED_PROMPTS };
