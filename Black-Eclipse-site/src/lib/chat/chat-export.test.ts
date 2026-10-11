import { describe, expect, it } from 'vitest';
import {
  buildExport,
  CHAT_EXPORT_KIND,
  mergeImport,
  parseImport,
  serializeExport,
} from './chat-export';
import type { ChatFolder, Conversation } from './chat-organization';

const conv = (id: string, extra: Partial<Conversation> = {}): Conversation => ({
  id,
  title: id,
  messages: [],
  timestamp: 0,
  createdAt: 0,
  folderId: null,
  color: null,
  pinned: false,
  tags: [],
  archivedAt: null,
  deletedAt: null,
  ...extra,
});

const folder = (id: string): ChatFolder => ({ id, name: id, color: '#000' });

describe('chat export', () => {
  it('wraps the store in a versioned envelope', () => {
    const payload = buildExport([conv('a')], [folder('f')], 0);
    expect(payload.kind).toBe(CHAT_EXPORT_KIND);
    expect(payload.version).toBe(1);
    expect(JSON.parse(serializeExport([conv('a')], [folder('f')], 0))).toEqual(payload);
  });

  it('parses its own output round-trip', () => {
    const parsed = parseImport(serializeExport([conv('a', { tags: ['x'] })], [folder('f')], 0));
    expect(parsed.conversations[0]).toMatchObject({ id: 'a', tags: ['x'] });
    expect(parsed.folders[0].id).toBe('f');
  });

  it('accepts a bare { conversations, folders } object', () => {
    const parsed = parseImport(JSON.stringify({ conversations: [{ id: 'a', messages: [] }], folders: [] }));
    expect(parsed.conversations).toHaveLength(1);
  });

  it('rejects junk, foreign kinds and empty payloads', () => {
    expect(() => parseImport('{not json')).toThrow();
    expect(() => parseImport(JSON.stringify({ kind: 'something-else' }))).toThrow();
    expect(() => parseImport(JSON.stringify({ conversations: [], folders: [] }))).toThrow('Nothing to import');
  });

  it('merges additively and keeps existing records on id collision', () => {
    const existing = [conv('a', { title: 'local' })];
    const res = mergeImport(existing, [folder('f')], {
      conversations: [conv('a', { title: 'imported' }), conv('b')],
      folders: [folder('f'), folder('g')],
    });
    expect(res.addedConversations).toBe(1);
    expect(res.addedFolders).toBe(1);
    expect(res.conversations.find((c) => c.id === 'a')?.title).toBe('local');
    expect(res.conversations.map((c) => c.id).sort()).toEqual(['a', 'b']);
    expect(res.folders.map((f) => f.id).sort()).toEqual(['f', 'g']);
  });
});
