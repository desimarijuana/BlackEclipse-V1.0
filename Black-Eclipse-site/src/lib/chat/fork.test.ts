import { describe, expect, it } from 'vitest';
import type { Conversation } from './chat-organization';
import { cloneMessages, forkConversation, forkTitle, newChatId } from './fork';

function conv(partial: Partial<Conversation> = {}): Conversation {
  return {
    id: 'chat_source',
    title: 'NVDA research',
    messages: [
      { id: 'u1', role: 'user', content: 'Research NVDA' },
      { id: 'a1', role: 'assistant', content: 'NVDA is...' },
      { id: 'u2', role: 'user', content: 'And AMD?' },
      { id: 'a2', role: 'assistant', content: 'AMD is...' },
    ],
    timestamp: 100,
    createdAt: 50,
    folderId: 'folder_1',
    color: '#fff',
    tags: ['semis'],
    pinned: true,
    ...partial,
  };
}

describe('newChatId', () => {
  it('produces a session-store-safe, unique id', () => {
    const a = newChatId(1, 0.1);
    const b = newChatId(1, 0.2);
    expect(a).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
    expect(a).not.toBe(b);
  });
});

describe('forkTitle', () => {
  it('suffixes and tolerates an empty title', () => {
    expect(forkTitle('NVDA research')).toBe('NVDA research (fork)');
    expect(forkTitle('')).toBe('Untitled Session (fork)');
  });
});

describe('cloneMessages', () => {
  it('gives every message a fresh id and preserves content', () => {
    const cloned = cloneMessages(conv().messages, { newMessageId: (i) => `new_${i}` });
    expect(cloned.map((m) => m.id)).toEqual(['new_0', 'new_1', 'new_2', 'new_3']);
    expect(cloned.map((m) => m.content)).toEqual(conv().messages.map((m) => m.content));
  });

  it('remaps a quote source to the cloned id', () => {
    const messages = [
      { id: 'a1', role: 'assistant' as const, content: 'x' },
      {
        id: 'u2',
        role: 'user' as const,
        content: 'what about this?',
        quote: { text: 'x', messageId: 'a1', role: 'assistant' as const },
      },
    ];
    const cloned = cloneMessages(messages, { newMessageId: (i) => `new_${i}` });
    expect(cloned[1].quote?.messageId).toBe('new_0');
  });

  it('clears live-only approval and clarification state', () => {
    const messages = [
      {
        id: 'a1',
        role: 'assistant' as const,
        content: '',
        pendingApproval: { id: 'ap' } as never,
        pendingClarification: { id: 'cl' } as never,
      },
    ];
    const cloned = cloneMessages(messages, { newMessageId: () => 'new' });
    expect(cloned[0].pendingApproval).toBeUndefined();
    expect(cloned[0].pendingClarification).toBeUndefined();
  });
});

describe('forkConversation', () => {
  it('forks the whole conversation and snapshots provenance', () => {
    const source = conv();
    const fork = forkConversation(source, { now: 999, newChatId: () => 'chat_fork', newMessageId: (i) => `m_${i}` });
    expect(fork.id).toBe('chat_fork');
    expect(fork.title).toBe('NVDA research (fork)');
    expect(fork.messages).toHaveLength(4);
    expect(fork.messages.map((m) => m.id)).toEqual(['m_0', 'm_1', 'm_2', 'm_3']);
    expect(fork.forkedFrom).toEqual({ conversationId: 'chat_source', title: 'NVDA research', at: 999 });
    expect(fork.folderId).toBe('folder_1');
    expect(fork.color).toBe('#fff');
    expect(fork.tags).toEqual(['semis']);
    expect(fork.pinned).toBe(false);
    expect(fork.timestamp).toBe(999);
    expect(source.messages[0].id).toBe('u1');
  });

  it('forks through a chosen message inclusive', () => {
    const fork = forkConversation(conv(), {
      messageId: 'a1',
      now: 1,
      newChatId: () => 'chat_fork',
      newMessageId: (i) => `m_${i}`,
    });
    expect(fork.messages.map((m) => m.content)).toEqual(['Research NVDA', 'NVDA is...']);
    expect(fork.forkedFrom?.messageId).toBe('a1');
  });

  it('falls back to the whole conversation when the message id is gone', () => {
    const fork = forkConversation(conv(), { messageId: 'missing', now: 1, newChatId: () => 'f', newMessageId: (i) => `m_${i}` });
    expect(fork.messages).toHaveLength(4);
  });
});
