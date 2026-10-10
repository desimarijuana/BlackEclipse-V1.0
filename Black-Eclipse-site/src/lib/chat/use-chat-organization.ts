'use client';

import { useCallback, useRef, useState } from 'react';
import {
  DEFAULT_FOLDER_COLOR,
  loadFolders,
  saveFolders,
  type ChatFolder,
  type ChatOrganizationApi,
  type Conversation,
} from '@/lib/chat/chat-organization';

/**
 * Owns the chat-organization metadata (folders, pin, color, rename, move) that
 * is layered over the sidebar's conversation list.
 *
 * Folder state lives here; conversation metadata is mutated through the `patch`
 * callback so this hook does not need to own the transcript store (which stays
 * in the chat screen). `patch` receives a pure updater over the current list and
 * is responsible for persisting the result.
 */
export function useChatOrganization(patch: (update: (list: Conversation[]) => Conversation[]) => void): ChatOrganizationApi {
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

  const createFolder = useCallback(() => {
    const folder: ChatFolder = { id: 'folder_' + Date.now(), name: 'New Folder', color: DEFAULT_FOLDER_COLOR };
    save([...foldersRef.current, folder]);
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

  const deleteFolder = useCallback((id: string) => {
    save(foldersRef.current.filter((f) => f.id !== id));
    // Unfile the folder's chats rather than orphaning them on a dangling id.
    patch((list) => list.map((c) => (c.folderId === id ? { ...c, folderId: null } : c)));
  }, [save, patch]);

  const patchConversation = useCallback(
    (id: string, fields: Partial<Conversation>) => {
      patch((list) => list.map((c) => (c.id === id ? { ...c, ...fields } : c)));
    },
    [patch],
  );

  const moveConversation = useCallback(
    (id: string, folderId: string | null) => patchConversation(id, { folderId }),
    [patchConversation],
  );
  const setConversationColor = useCallback(
    (id: string, color: string | null) => patchConversation(id, { color }),
    [patchConversation],
  );
  const renameConversation = useCallback(
    (id: string, title: string) => patchConversation(id, { title }),
    [patchConversation],
  );
  const togglePin = useCallback(
    (id: string) => patch((list) => list.map((c) => (c.id === id ? { ...c, pinned: !c.pinned } : c))),
    [patch],
  );

  return {
    folders,
    load,
    createFolder,
    renameFolder,
    deleteFolder,
    toggleFolder,
    setFolderColor,
    moveConversation,
    setConversationColor,
    togglePin,
    renameConversation,
  };
}
