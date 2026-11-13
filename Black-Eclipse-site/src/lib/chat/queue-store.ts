'use client';

// ── Durable, cross-tab prompt queue ──────────────────────────────────────────
//
// The in-memory queue was lost when its tab closed and could not be shared with
// another tab. This store persists every conversation's queue in localStorage
// and broadcasts changes over BroadcastChannel. Dequeue is serialized with a
// per-chat Web Lock so two tabs cannot take the same prompt.

import type { MessageQuote } from '@/types/chat';
import { MAX_QUEUED_PROMPTS, enqueuePrompt, type QueuedPrompt } from './message-queue';

const STORAGE_KEY = 'eclipse.promptQueues.v1';
const CHANNEL_NAME = 'eclipse.queue.v1';

export interface StoredQueue {
  items: QueuedPrompt[];
  paused?: boolean;
  updatedAt: number;
}

type QueueBook = { version: 1; queues: Record<string, StoredQueue> };
type Listener = () => void;

const localListeners = new Set<Listener>();
let channel: BroadcastChannel | null = null;
let bound = false;
// Private mode / blocked storage still gets a working queue for this session.
let memoryBook: QueueBook = { version: 1, queues: {} };

function storage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

function emptyBook(): QueueBook {
  return { version: 1, queues: {} };
}

function readBook(): QueueBook {
  try {
    const store = storage();
    if (!store) return memoryBook;
    const raw = store.getItem(STORAGE_KEY);
    if (!raw) return emptyBook();
    const parsed = JSON.parse(raw) as QueueBook;
    if (!parsed || parsed.version !== 1 || !parsed.queues || typeof parsed.queues !== 'object') {
      return emptyBook();
    }
    return parsed;
  } catch {
    return emptyBook();
  }
}

function notifyLocal(): void {
  for (const listener of localListeners) {
    try {
      listener();
    } catch {
      /* a broken subscriber must not stop the others */
    }
  }
}

function writeBook(book: QueueBook): void {
  try {
    const store = storage();
    if (!store) {
      memoryBook = book;
      notifyLocal();
      return;
    }
    if (Object.keys(book.queues).length === 0) store.removeItem(STORAGE_KEY);
    else store.setItem(STORAGE_KEY, JSON.stringify(book));
  } catch {
    memoryBook = book;
  }
  notifyLocal();
  try {
    channel?.postMessage({ type: 'changed' });
  } catch {
    /* a closed channel must not break a send */
  }
}

function ensureChannel(): void {
  if (bound || typeof window === 'undefined') return;
  bound = true;
  if (typeof BroadcastChannel !== 'undefined') {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.addEventListener('message', () => notifyLocal());
  }
  window.addEventListener('storage', (event) => {
    if (event.key === STORAGE_KEY) notifyLocal();
  });
}

export function subscribeQueueStore(listener: Listener): () => void {
  ensureChannel();
  localListeners.add(listener);
  return () => localListeners.delete(listener);
}

function queueFor(book: QueueBook, chatId: string): StoredQueue {
  const existing = book.queues[chatId];
  if (existing) {
    if (!Array.isArray(existing.items)) existing.items = [];
    return existing;
  }
  const created: StoredQueue = { items: [], updatedAt: Date.now() };
  book.queues[chatId] = created;
  return created;
}

function newId(): string {
  return `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function allQueued(): QueuedPrompt[] {
  const book = readBook();
  return Object.values(book.queues).flatMap((queue) => queue.items);
}

export function queuedFor(chatId: string | null | undefined): QueuedPrompt[] {
  if (!chatId) return allQueued().filter((item) => !item.chatId);
  return readBook().queues[chatId]?.items ?? [];
}

export function enqueueStored(
  chatId: string,
  text: string,
  quote?: MessageQuote,
): QueuedPrompt | null {
  const book = readBook();
  const queue = queueFor(book, chatId);
  const before = queue.items.length;
  const next = enqueuePrompt(queue.items, text, newId, Date.now(), quote, chatId);
  if (next.length === before) return null;
  queue.items = [...next].slice(-MAX_QUEUED_PROMPTS);
  queue.updatedAt = Date.now();
  writeBook(book);
  return queue.items[queue.items.length - 1] ?? null;
}

export function removeStored(chatId: string, id: string): void {
  const book = readBook();
  const queue = book.queues[chatId];
  if (!queue) return;
  const next = queue.items.filter((item) => item.id !== id);
  if (next.length === queue.items.length) return;
  queue.items = next;
  queue.updatedAt = Date.now();
  writeBook(book);
}

export function updateStored(chatId: string, id: string, text: string): void {
  const trimmed = text.trim();
  const book = readBook();
  const queue = book.queues[chatId];
  if (!queue) return;
  if (!trimmed) {
    removeStored(chatId, id);
    return;
  }
  queue.items = queue.items.map((item) => (item.id === id ? { ...item, text: trimmed } : item));
  queue.updatedAt = Date.now();
  writeBook(book);
}

export function moveStored(chatId: string, id: string, direction: 'up' | 'down'): void {
  const book = readBook();
  const queue = book.queues[chatId];
  if (!queue) return;
  const index = queue.items.findIndex((item) => item.id === id);
  const target = direction === 'up' ? index - 1 : index + 1;
  if (index < 0 || target < 0 || target >= queue.items.length) return;
  const next = [...queue.items];
  [next[index], next[target]] = [next[target], next[index]];
  queue.items = next;
  queue.updatedAt = Date.now();
  writeBook(book);
}

export function promoteStored(chatId: string, id: string): void {
  const book = readBook();
  const queue = book.queues[chatId];
  if (!queue) return;
  const index = queue.items.findIndex((item) => item.id === id);
  if (index <= 0) return;
  queue.items = [queue.items[index], ...queue.items.slice(0, index), ...queue.items.slice(index + 1)];
  queue.updatedAt = Date.now();
  writeBook(book);
}

export function clearStored(chatId?: string | null): void {
  const book = readBook();
  if (chatId === undefined) {
    writeBook(emptyBook());
    return;
  }
  if (chatId === null) {
    for (const key of Object.keys(book.queues)) {
      book.queues[key].items = book.queues[key].items.filter((item) => item.chatId);
      book.queues[key].updatedAt = Date.now();
    }
  } else {
    delete book.queues[chatId];
  }
  writeBook(book);
}

export function isQueuePaused(chatId: string | null | undefined): boolean {
  if (!chatId) return false;
  return readBook().queues[chatId]?.paused === true;
}

export function setQueuePaused(chatId: string, paused: boolean): void {
  const book = readBook();
  const queue = queueFor(book, chatId);
  queue.paused = paused;
  queue.updatedAt = Date.now();
  writeBook(book);
}

async function withQueueLock<T>(chatId: string, fn: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== 'undefined'
    ? (navigator as Navigator & { locks?: LockManager }).locks
    : undefined;
  if (locks?.request) {
    return locks.request(`eclipse-queue:${chatId}`, fn) as unknown as Promise<T>;
  }
  return fn();
}

/**
 * Atomically take the head of a conversation's queue. The Web Lock makes two
 * tabs take DIFFERENT prompts, so neither duplicates a user turn.
 */
export async function takeNextFor(chatId: string): Promise<QueuedPrompt | null> {
  return withQueueLock(chatId, async () => {
    const book = readBook();
    const queue = book.queues[chatId];
    if (!queue || queue.paused || queue.items.length === 0) return null;
    const [item, ...rest] = queue.items;
    queue.items = rest;
    queue.updatedAt = Date.now();
    writeBook(book);
    return item ?? null;
  });
}

export { STORAGE_KEY as PROMPT_QUEUE_STORAGE_KEY };
