import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  PROMPT_QUEUE_STORAGE_KEY,
  allQueued,
  clearStored,
  enqueueStored,
  isQueuePaused,
  setQueuePaused,
  takeNextFor,
} from './queue-store';

const store = new Map<string, string>();
const fakeStorage = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => {
    store.set(key, value);
  },
  removeItem: (key: string) => {
    store.delete(key);
  },
};

beforeEach(() => {
  store.clear();
  vi.stubGlobal('window', {
    localStorage: fakeStorage,
    addEventListener: () => undefined,
  });
  vi.stubGlobal('BroadcastChannel', undefined);
});

describe('durable prompt queue', () => {
  it('persists prompts and dequeues one atomically', async () => {
    expect(enqueueStored('chat_a', 'first')).toMatchObject({ text: 'first', chatId: 'chat_a' });
    expect(enqueueStored('chat_a', 'second')).toMatchObject({ text: 'second' });
    expect(allQueued().map((item) => item.text)).toEqual(['first', 'second']);

    const taken = await takeNextFor('chat_a');
    expect(taken?.text).toBe('first');
    expect(allQueued().map((item) => item.text)).toEqual(['second']);
  });

  it('holds the queue while paused', async () => {
    enqueueStored('chat_b', 'wait');
    setQueuePaused('chat_b', true);
    expect(isQueuePaused('chat_b')).toBe(true);
    expect(await takeNextFor('chat_b')).toBeNull();

    setQueuePaused('chat_b', false);
    expect((await takeNextFor('chat_b'))?.text).toBe('wait');
  });

  it('clears only the requested conversation', () => {
    enqueueStored('chat_c', 'keep');
    enqueueStored('chat_d', 'drop');
    clearStored('chat_d');
    expect(allQueued().map((item) => item.text)).toEqual(['keep']);
    expect(store.has(PROMPT_QUEUE_STORAGE_KEY)).toBe(true);
  });
});
