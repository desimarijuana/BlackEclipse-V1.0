import { describe, expect, it } from 'vitest';
import {
  buildChatHistoryView,
  buildFolderTree,
  collectTags,
  filterConversations,
  flattenFolderTree,
  folderSubtreeIds,
  groupConversations,
  inScope,
  loadFolders,
  matchesQuery,
  normalizeConversation,
  normalizeConversations,
  normalizeFolders,
  saveFolders,
  scoreConversation,
  searchConversations,
  sortConversations,
  wouldCycle,
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

  it('backfills createdAt and defaults organization fields', () => {
    expect(normalizeConversation({ id: 'a', title: 'A', messages: [], timestamp: 123 })).toEqual({
      id: 'a',
      title: 'A',
      messages: [],
      timestamp: 123,
      createdAt: 123,
      folderId: null,
      color: null,
      pinned: false,
      tags: [],
      archivedAt: null,
      deletedAt: null,
    });
  });

  it('preserves and normalises tags, archive and trash stamps', () => {
    const c = normalizeConversation({
      id: 'a',
      title: 'A',
      messages: [],
      timestamp: 5,
      tags: ['  Earnings ', 'earnings', 'MACRO', 42],
      archivedAt: 10,
      deletedAt: 20,
    });
    expect(c?.tags).toEqual(['earnings', 'macro']);
    expect(c).toMatchObject({ archivedAt: 10, deletedAt: 20 });
  });

  it('filters malformed messages and drops unusable rows', () => {
    expect(normalizeConversation({ id: 'a', messages: [{ id: 'm', role: 'user', content: 'x' }, { nope: true }, 'junk'] })?.messages).toHaveLength(1);
    expect(normalizeConversations([{ id: 'a' }, {}, null, { id: 'b' }])).toHaveLength(2);
    expect(normalizeConversations('nope')).toEqual([]);
  });
});

describe('scope & tags', () => {
  it('inScope splits active/archived/trash', () => {
    expect(inScope(conv({ id: 'a' }), 'active')).toBe(true);
    expect(inScope(conv({ id: 'a', archivedAt: 1 }), 'active')).toBe(false);
    expect(inScope(conv({ id: 'a', archivedAt: 1 }), 'archived')).toBe(true);
    expect(inScope(conv({ id: 'a', deletedAt: 1 }), 'archived')).toBe(false);
    expect(inScope(conv({ id: 'a', deletedAt: 1 }), 'trash')).toBe(true);
  });

  it('collectTags de-duplicates and sorts', () => {
    expect(collectTags([conv({ id: 'a', tags: ['macro', 'earnings'] }), conv({ id: 'b', tags: ['earnings'] })])).toEqual(['earnings', 'macro']);
  });
});

describe('search', () => {
  const c = conv({
    id: 'a',
    title: 'Tesla earnings',
    messages: [{ id: 'm', role: 'user', content: 'What about Nvidia and its data center revenue?' }],
    tags: ['ev'],
  });

  it('matches title, body and tags case-insensitively', () => {
    expect(matchesQuery(c, 'tesla')).toBe(true);
    expect(matchesQuery(c, 'nvidia')).toBe(true);
    expect(matchesQuery(c, 'ev')).toBe(true);
    expect(matchesQuery(c, 'nothing')).toBe(false);
  });

  it('requires every token (AND semantics)', () => {
    expect(matchesQuery(c, 'tesla nvidia')).toBe(true);
    expect(matchesQuery(c, 'tesla apple')).toBe(false);
  });

  it('ranks title hits above body hits', () => {
    const titleHit = conv({ id: '1', title: 'gold outlook' });
    const bodyHit = conv({ id: '2', title: 'misc', messages: [{ id: 'm', role: 'user', content: 'gold is up' }] });
    const ranked = searchConversations([bodyHit, titleHit], 'gold');
    expect(ranked.map((h) => h.conversation.id)).toEqual(['1', '2']);
  });

  it('produces a body snippet around the match', () => {
    const hit = scoreConversation(c, 'nvidia');
    expect(hit?.snippet).toContain('Nvidia');
  });

  it('empty query matches everything', () => {
    expect(filterConversations([c], '  ')).toEqual([c]);
  });
});

describe('sortConversations', () => {
  const a = conv({ id: 'a', title: 'Bravo', timestamp: 1 });
  const b = conv({ id: 'b', title: 'Alpha', timestamp: 3 });
  const p = conv({ id: 'p', title: 'Zulu', timestamp: 2, pinned: true });

  it('pins first then sorts by recency / alpha / created', () => {
    expect(sortConversations([a, b, p], 'recent').map((c) => c.id)).toEqual(['p', 'b', 'a']);
    expect(sortConversations([a, b], 'alpha').map((c) => c.id)).toEqual(['b', 'a']);
  });
});

describe('folder tree', () => {
  const folders: ChatFolder[] = [
    { id: 'root', name: 'Research', color: '#000', order: 0 },
    { id: 'child', name: 'Energy', color: '#000', parentId: 'root', order: 0 },
    { id: 'root2', name: 'Archive', color: '#000', order: 1 },
  ];

  it('builds and flattens a forest pre-order with depth', () => {
    const flat = flattenFolderTree(buildFolderTree(folders));
    expect(flat.map((n) => [n.folder.id, n.depth])).toEqual([['root', 0], ['child', 1], ['root2', 0]]);
  });

  it('detects cycles', () => {
    expect(wouldCycle(folders, 'root', 'child')).toBe(true);
    expect(wouldCycle(folders, 'child', 'root2')).toBe(false);
  });

  it('treats a cyclic parent as a root rather than losing the folder', () => {
    const cyclic: ChatFolder[] = [
      { id: 'a', name: 'A', color: '#000', parentId: 'b' },
      { id: 'b', name: 'B', color: '#000', parentId: 'a' },
    ];
    const flat = flattenFolderTree(buildFolderTree(cyclic));
    expect(flat.map((n) => n.folder.id).sort()).toEqual(['a', 'b']);
  });

  it('lists a subtree', () => {
    expect(folderSubtreeIds(folders, 'root').sort()).toEqual(['child', 'root']);
  });
});

describe('groupConversations', () => {
  const folders: ChatFolder[] = [
    { id: 'f1', name: 'Research', color: '#000', order: 0 },
    { id: 'f2', name: 'Empty', color: '#000', order: 1 },
  ];

  it('keeps empty folders and nests by depth', () => {
    const groups = groupConversations(
      [conv({ id: 'a', folderId: 'f1' }), conv({ id: 'b', folderId: 'gone' }), conv({ id: 'c' })],
      folders,
    );
    expect(groups.map((g) => [g.folder?.id ?? null, g.depth])).toEqual([['f1', 0], ['f2', 0], [null, 0]]);
    expect(groups[1].conversations).toEqual([]);
    expect(groups[2].conversations.map((c) => c.id)).toEqual(['b', 'c']);
  });
});

describe('buildChatHistoryView', () => {
  const folders: ChatFolder[] = [{ id: 'f1', name: 'Research', color: '#000' }];

  it('splits pinned out of folder groups', () => {
    const view = buildChatHistoryView([conv({ id: 'a', folderId: 'f1' }), conv({ id: 'p', pinned: true })], folders);
    expect(view.pinned.map((c) => c.id)).toEqual(['p']);
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
  });

  it('flattens archive/trash scope and filters by tag', () => {
    const data = [conv({ id: 'x', archivedAt: 1, tags: ['macro'] }), conv({ id: 'y' })];
    const archived = buildChatHistoryView(data, folders, { scope: 'archived' });
    expect(archived.groups[0].conversations.map((c) => c.id)).toEqual(['x']);
    const tagged = buildChatHistoryView([...data, conv({ id: 'z', tags: ['macro'] })], folders, { tag: 'macro' });
    // 'x' is archived, so it is out of the active scope; only 'z' matches.
    expect(tagged.matches).toBe(1);
  });
});

describe('storage', () => {
  it('round-trips folders and tolerates junk', () => {
    const s = memStorage();
    const folders: ChatFolder[] = [{ id: 'f1', name: 'Research', color: '#3b82f6', parentId: 'root', order: 2 }];
    saveFolders(s, folders);
    expect(loadFolders(s)).toEqual(folders);
    s.setItem('chat_folders_v1', '{bad json');
    expect(loadFolders(s)).toEqual([]);
    expect(normalizeFolders([{ name: 'no-id' }, { id: 'f2' }])).toEqual([{ id: 'f2', name: 'Folder', color: '#64748b' }]);
  });
});
