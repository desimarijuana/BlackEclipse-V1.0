import { describe, expect, it } from 'vitest';
import {
  buildChatHistoryView,
  filterConversations,
  groupConversations,
  loadFolders,
  matchesQuery,
  normalizeConversation,
  normalizeConversations,
  saveFolders,
  sortConversations,
  type ChatFolder,
  type Conversation,
} from './chat-organization';

function conv(partial: Partial<Conversation> & { id: string }): Conversation {
  return {
    title: partial.id,
    messages: [],
    timestamp: 0,
    ...partial,
    createdAt: partial.createdAt ?? partial.timestamp ?? 0,
  };
}

const memStorage = () => {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
  };
};

describe('normalizeConversation', () => {
  it('drops rows without an id', () => {
    expect(normalizeConversation(null)).toBeNull();
    expect(normalizeConversation({ title: 'x' })).toBeNull();
  });

  it('backfills createdAt from timestamp and defaults organization fields', () => {
    const c = normalizeConversation({ id: 'a', title: 'A', messages: [], timestamp: 123 });
    expect(c).toEqual({
      id: 'a',
      title: 'A',
      messages: [],
      timestamp: 123,
      createdAt: 123,
      folderId: null,
      color: null,
      pinned: false,
    });
  });

  it('preserves explicit organization fields', () => {
    const c = normalizeConversation({
      id: 'a',
      title: 'A',
      messages: [{ id: 'm', role: 'user', content: 'hi' }],
      timestamp: 5,
      createdAt: 1,
      folderId: 'f1',
      color: '#ef4444',
      pinned: true,
    });
    expect(c).toMatchObject({ createdAt: 1, folderId: 'f1', color: '#ef4444', pinned: true });
  });

  it('filters malformed messages', () => {
    const c = normalizeConversation({ id: 'a', messages: [{ id: 'm', role: 'user', content: 'x' }, { nope: true }, 'junk'] });
    expect(c?.messages).toHaveLength(1);
  });

  it('normalizeConversations drops unusable rows', () => {
    expect(normalizeConversations([{ id: 'a' }, {}, null, { id: 'b' }])).toHaveLength(2);
    expect(normalizeConversations('nope')).toEqual([]);
  });
});

describe('search', () => {
  const c = conv({
    id: 'a',
    title: 'Tesla earnings',
    messages: [{ id: 'm', role: 'user', content: 'What about Nvidia?' }],
  });

  it('matches titles case-insensitively', () => {
    expect(matchesQuery(c, 'tesla')).toBe(true);
    expect(matchesQuery(c, 'nothing')).toBe(false);
  });

  it('matches message bodies', () => {
    expect(matchesQuery(c, 'nvidia')).toBe(true);
  });

  it('empty query matches everything', () => {
    expect(filterConversations([c], '  ')).toEqual([c]);
  });
});

describe('sortConversations', () => {
  const a = conv({ id: 'a', title: 'Bravo', timestamp: 1, pinned: false });
  const b = conv({ id: 'b', title: 'Alpha', timestamp: 3, pinned: false });
  const p = conv({ id: 'p', title: 'Zulu', timestamp: 2, pinned: true });

  it('pins first then sorts by recency', () => {
    expect(sortConversations([a, b, p], 'recent').map((c) => c.id)).toEqual(['p', 'b', 'a']);
  });

  it('sorts alphabetically', () => {
    expect(sortConversations([a, b], 'alpha').map((c) => c.id)).toEqual(['b', 'a']);
  });

  it('sorts by createdAt', () => {
    const old = conv({ id: 'old', timestamp: 100, createdAt: 1 });
    const fresh = conv({ id: 'fresh', timestamp: 2, createdAt: 99 });
    expect(sortConversations([old, fresh], 'created').map((c) => c.id)).toEqual(['fresh', 'old']);
  });
});

describe('groupConversations', () => {
  const folders: ChatFolder[] = [
    { id: 'f1', name: 'Research', color: '#000' },
    { id: 'f2', name: 'Empty', color: '#000' },
  ];

  it('buckets by folder, puts unknown/unfiled in the trailing null group, and keeps empty folders', () => {
    const groups = groupConversations(
      [conv({ id: 'a', folderId: 'f1' }), conv({ id: 'b', folderId: 'gone' }), conv({ id: 'c' })],
      folders,
    );
    expect(groups.map((g) => g.folder?.id ?? null)).toEqual(['f1', 'f2', null]);
    expect(groups[0].conversations.map((c) => c.id)).toEqual(['a']);
    expect(groups[1].conversations).toEqual([]);
    expect(groups[2].conversations.map((c) => c.id)).toEqual(['b', 'c']);
  });
});

describe('buildChatHistoryView', () => {
  const folders: ChatFolder[] = [{ id: 'f1', name: 'Research', color: '#000' }];

  it('splits pinned out of folder groups', () => {
    const view = buildChatHistoryView(
      [conv({ id: 'a', folderId: 'f1' }), conv({ id: 'p', pinned: true })],
      folders,
    );
    expect(view.pinned.map((c) => c.id)).toEqual(['p']);
    expect(view.groups).toHaveLength(1);
    expect(view.groups[0].conversations.map((c) => c.id)).toEqual(['a']);
  });

  it('flattens into a single group while searching', () => {
    const view = buildChatHistoryView(
      [conv({ id: 'a', title: 'alpha', folderId: 'f1' }), conv({ id: 'b', title: 'beta' })],
      folders,
      { query: 'beta' },
    );
    expect(view.pinned).toEqual([]);
    expect(view.groups).toHaveLength(1);
    expect(view.groups[0].folder).toBeNull();
    expect(view.groups[0].conversations.map((c) => c.id)).toEqual(['b']);
    expect(view.matches).toBe(1);
    expect(view.total).toBe(2);
  });
});

describe('folder storage', () => {
  it('round-trips and tolerates junk', () => {
    const s = memStorage();
    const folders: ChatFolder[] = [{ id: 'f1', name: 'Research', color: '#3b82f6' }];
    saveFolders(s, folders);
    expect(loadFolders(s)).toEqual(folders);
    s.setItem('chat_folders_v1', '{bad json');
    expect(loadFolders(s)).toEqual([]);
    s.setItem('chat_folders_v1', JSON.stringify([{ name: 'no-id' }, { id: 'f2' }]));
    expect(loadFolders(s)).toEqual([{ id: 'f2', name: 'Folder', color: '#64748b' }]);
  });
});
