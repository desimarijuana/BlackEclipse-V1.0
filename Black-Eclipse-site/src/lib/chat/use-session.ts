'use client';

// Client hook owning a conversation's session workspace: the loaded listing,
// uploads, deletes, and a refresh trigger. Shared so the composer's Plus button
// and the session bar act on the same state instead of each fetching their own.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deleteSessionFile,
  fetchSession,
  uploadSessionFile,
} from './session-client';
import { SESSION_LIMITS, type SessionFile, type SessionInfo } from './session-types';

export interface SessionController {
  session: SessionInfo | null;
  busy: boolean;
  error: string | null;
  refresh: () => void;
  uploadFiles: (files: FileList | File[]) => Promise<void>;
  removeFile: (file: SessionFile) => Promise<void>;
}

export function useSession(chatId: string | null, refreshKey = 0): SessionController {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localKey, setLocalKey] = useState(0);
  const chatIdRef = useRef(chatId);
  chatIdRef.current = chatId;
  // Files attached before a conversation exists, flushed on the first reload.
  const pendingRef = useRef<File[]>([]);

  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    const id = chatIdRef.current;
    const list = Array.from(files);
    if (list.length === 0) return;
    // No conversation yet (empty state): hold the files and flush them once the
    // first message creates the chat, so attaching before sending still works.
    if (!id) {
      pendingRef.current.push(...list);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      for (const file of list) {
        if (file.size > SESSION_LIMITS.maxFileBytes) {
          throw new Error(
            `${file.name} exceeds ${Math.round(SESSION_LIMITS.maxFileBytes / 1024 / 1024)}MB`
          );
        }
        const bytes = new Uint8Array(await file.arrayBuffer());
        await uploadSessionFile(id, 'context', file.name, bytes);
      }
      setLocalKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }, []);

  const reload = useCallback(async () => {
    const id = chatIdRef.current;
    if (!id) {
      setSession(null);
      return;
    }
    try {
      // A conversation now exists: flush anything attached beforehand.
      if (pendingRef.current.length > 0) {
        const queued = pendingRef.current;
        pendingRef.current = [];
        await uploadFiles(queued);
      }
      const next = await fetchSession(id);
      // Ignore a response for a conversation the user has since left.
      if (chatIdRef.current === id) {
        setSession(next);
        setError(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load session folder');
    }
  }, [uploadFiles]);

  useEffect(() => { void reload(); }, [reload, refreshKey, localKey]);

  const refresh = useCallback(() => setLocalKey((k) => k + 1), []);

  const removeFile = useCallback(async (file: SessionFile) => {
    const id = chatIdRef.current;
    if (!id) return;
    setBusy(true);
    try {
      await deleteSessionFile(id, file.kind, file.name);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  return { session, busy, error, refresh, uploadFiles, removeFile };
}
