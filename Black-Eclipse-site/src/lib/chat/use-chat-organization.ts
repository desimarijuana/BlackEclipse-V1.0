'use client';

import { useCallback, useRef, useState } from 'react';
import {
  DEFAULT_FOLDER_COLOR,
  loadFolders,
  normalizeTag,
  saveFolders,
  wouldCycle,
  type ChatFolder,
  type ChatOrganizationApi,
  type Conversation,
} from '@/lib/chat/chat-organization';
import { mergeImport, parseImport } from '@/lib/chat/chat-export';

/** Bridge to the conversation store, owned by the chat screen. */
type Patch = (update: (list: Conversation[]) => Conversation[]) => void;

/**
 * Owns the chat-organization metadata (nested folders, tags, colors, pin,
 * rename, move, archive, trash) layered over the sidebar's conversation list.
 * Folder state lives here; conversations are mutated through `patch`.
 */
export function useChatOrganization(patch: Patch): ChatOrganizationApi {
  const [folders, setFolders] = useState<ChatFolder[]>([]);
  const foldersRef = useRef<ChatFolder[]>([]);

  const load = useCallback(() => {
    const loaded = loadFolders(localStorage);
    foldersRef.current = loaded;
    setFolders(loaded);
  }, []);

  const save = useCallback((updated: ChatFolder[]) => {
    foldersRef.current = updated;
    setFolders(updated);
    saveFolders(localStorage, updated);
  }, []);

  /** Apply a per-conversation field patch to a set of ids. */
  const patchConvs = useCallback(
    (ids: string[], fields: (c: Conversation) => Partial<Conversation>) => {
      const set = new Set(ids);
      patch((list) => list.map((c) => (set.has(c.id) ? { ...c, ...fields(c) } : c)));
    },
    [patch],
  );

  // ── Folders ────────────────────────────────────────────────────────────────
  const createFolder = useCallback((name?: string) => {
    const id = 'folder_' + Date.now() + Math.random().toString(36).slice(2, 6);
    const order = Math.max(-1, ...foldersRef.current.filter((f) => !f.parentId).map((f) => f.order ?? 0)) + 1;
    const folder: ChatFolder = { id, name: name?.trim() || 'New Folder', color: DEFAULT_FOLDER_COLOR, parentId: null, order };
    save([...foldersRef.current, folder]);
    return id;
  }, [save]);

  const renameFolder = useCallback((id: string, name: string) => {
    save(foldersRef.current.map((f) => (f.id === id ? { ...f, name } : f)));
  }, [save]);

  const setFolderColor = useCallback((id: string, color: string) => {
    save(foldersRef.current.map((f) => (f.id === id ? { ...f, color } : f)));
  }, [save]);

  const toggleFolder = useCallback((id: string) => {
    save(foldersRef.current.map((f) => (f.id === id ? { ...f, collapsed: !f.collapsed } : f)));
  }, [save]);

  /**
   * Delete a folder: its child folders move up to its parent, and chats filed
   * directly in it become unfiled. Descendants are left intact (they simply sit
   * one level higher).
   */
  const deleteFolder = useCallback((id: string) => {
    const parentId = foldersRef.current.find((f) => f.id === id)?.parentId ?? null;
    save(foldersRef.current.filter((f) => f.id !== id).map((f) => ((f.parentId ?? null) === id ? { ...f, parentId } : f)));
    patch((list) => list.map((c) => (c.folderId === id ? { ...c, folderId: null } : c)));
  }, [save, patch]);

  /** Reparent and/or reorder a folder among its siblings (cycle-safe). */
  const moveFolder = useCallback((id: string, parentId: string | null, beforeId: string | null) => {
    const all = foldersRef.current;
    const self = all.find((f) => f.id === id);
    if (!self || wouldCycle(all, id, parentId)) return;
    const siblings = all
      .filter((f) => (f.parentId ?? null) === parentId && f.id !== id)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name));
    const idx = beforeId ? siblings.findIndex((f) => f.id === beforeId) : siblings.length;
    siblings.splice(idx === -1 ? siblings.length : idx, 0, { ...self, parentId });
    const order = new Map(siblings.map((f, i) => [f.id, i]));
    save(all.map((f) => {
      if (f.id === id) return { ...f, parentId, order: order.get(id) };
      if ((f.parentId ?? null) === parentId && order.has(f.id)) return { ...f, order: order.get(f.id) };
      return f;
    }));
  }, [save]);

  // ── Conversations ──────────────────────────────────────────────────────────
  const moveConversation = useCallback((id: string, folderId: string | null) => {
    patchConvs([id], () => ({ folderId }));
  }, [patchConvs]);

  const setConversationColor = useCallback((id: string, color: string | null) => {
    patchConvs([id], () => ({ color }));
  }, [patchConvs]);

  const renameConversation = useCallback((id: string, title: string) => {
    patchConvs([id], () => ({ title }));
  }, [patchConvs]);

  const togglePin = useCallback((id: string) => {
    patch((list) => list.map((c) => (c.id === id ? { ...c, pinned: !c.pinned } : c)));
  }, [patch]);

  const addTag = useCallback((id: string, tag: string) => {
    const t = normalizeTag(tag);
    if (!t) return;
    patchConvs([id], (c) => ({ tags: (c.tags ?? []).includes(t) ? c.tags : [...(c.tags ?? []), t] }));
  }, [patchConvs]);

  const removeTag = useCallback((id: string, tag: string) => {
    const t = normalizeTag(tag);
    if (!t) return;
    patchConvs([id], (c) => ({ tags: (c.tags ?? []).filter((x) => x !== t) }));
  }, [patchConvs]);

  const archive = useCallback((id: string) => patchConvs([id], () => ({ archivedAt: Date.now() })), [patchConvs]);
  const unarchive = useCallback((id: string) => patchConvs([id], () => ({ archivedAt: null })), [patchConvs]);
  const trash = useCallback((id: string) => patchConvs([id], () => ({ deletedAt: Date.now() })), [patchConvs]);
  const restore = useCallback((id: string) => patchConvs([id], () => ({ deletedAt: null })), [patchConvs]);

  const purge = useCallback((id: string) => {
    patch((list) => list.filter((c) => c.id !== id));
  }, [patch]);
  const emptyTrash = useCallback(() => {
    patch((list) => list.filter((c) => !c.deletedAt));
  }, [patch]);

  // ── Bulk ───────────────────────────────────────────────────────────────────
  const bulkMove = useCallback((ids: string[], folderId: string | null) => patchConvs(ids, () => ({ folderId })), [patchConvs]);
  const bulkArchive = useCallback((ids: string[]) => patchConvs(ids, () => ({ archivedAt: Date.now() })), [patchConvs]);
  const bulkUnarchive = useCallback((ids: string[]) => patchConvs(ids, () => ({ archivedAt: null })), [patchConvs]);
  const bulkTrash = useCallback((ids: string[]) => patchConvs(ids, () => ({ deletedAt: Date.now() })), [patchConvs]);
  const bulkRestore = useCallback((ids: string[]) => patchConvs(ids, () => ({ deletedAt: null })), [patchConvs]);
  const bulkPin = useCallback((ids: string[], pinned: boolean) => patchConvs(ids, () => ({ pinned })), [patchConvs]);
  const bulkPurge = useCallback((ids: string[]) => {
    const set = new Set(ids);
    patch((list) => list.filter((c) => !set.has(c.id)));
  }, [patch]);

  // ── Import ─────────────────────────────────────────────────────────────────
  const importFromText = useCallback((text: string) => {
    try {
      const incoming = parseImport(text);
      let addedConversations = 0;
      let addedFolders = 0;
      let mergedFolders: ChatFolder[] = foldersRef.current;
      patch((list) => {
        const res = mergeImport(list, foldersRef.current, incoming);
        addedConversations = res.addedConversations;
        addedFolders = res.addedFolders;
        mergedFolders = res.folders;
        return res.conversations;
      });
      save(mergedFolders);
      return { addedConversations, addedFolders };
    } catch (e) {
      return { addedConversations: 0, addedFolders: 0, error: (e as Error).message };
    }
  }, [patch, save]);

  return {
    folders,
    load,
    createFolder,
    renameFolder,
    deleteFolder,
    toggleFolder,
    setFolderColor,
    moveFolder,
    moveConversation,
    setConversationColor,
    togglePin,
    renameConversation,
    addTag,
    removeTag,
    archive,
    unarchive,
    trash,
    restore,
    purge,
    emptyTrash,
    bulkMove,
    bulkArchive,
    bulkUnarchive,
    bulkTrash,
    bulkRestore,
    bulkPurge,
    bulkPin,
    importFromText,
  };
}
