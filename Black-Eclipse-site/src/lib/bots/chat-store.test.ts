import { beforeEach, describe, expect, it } from 'vitest';
import { useBotChatStore, type BotMessage } from './chat-store';

const scheduled = (runId: string, content = 'answer'): BotMessage & { runId: string } => ({
  id: `run-${runId}`,
  role: 'assistant',
  content,
  at: '2026-01-01T00:00:00Z',
  scheduled: true,
  runId,
});

describe('bot chat store — autonomous run append', () => {
  beforeEach(() => {
    useBotChatStore.getState().clear('b1');
  });

  it('appends a scheduled run exactly once, keyed by execution id', () => {
    const store = useBotChatStore.getState();
    expect(store.appendScheduled('b1', scheduled('e1'))).toBe(true);
    // A re-poll (or a reload that re-syncs history) must not double-post it.
    expect(useBotChatStore.getState().appendScheduled('b1', scheduled('e1'))).toBe(false);
    expect(useBotChatStore.getState().byBot['b1']).toHaveLength(1);
  });

  it('appends distinct runs in order', () => {
    const store = useBotChatStore.getState();
    store.appendScheduled('b1', scheduled('e1', 'first'));
    useBotChatStore.getState().appendScheduled('b1', scheduled('e2', 'second'));
    expect(useBotChatStore.getState().byBot['b1'].map((m) => m.content)).toEqual([
      'first',
      'second',
    ]);
  });
});
