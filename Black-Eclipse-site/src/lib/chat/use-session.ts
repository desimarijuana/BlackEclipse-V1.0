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

export interface PendingFile {
  name: string;
  bytes: number;
}

/**
 * The visible attachment chips: pending files first, then the session's saved
 * context files, de-duplicated by name (a file shown as pending must not appear
 * twice once it lands in the session). Pure, so the display rule is testable.
 */
export function mergeAttachmentChips(
  pending: PendingFile[],
  contextFiles: { name: string }[],
): { name: string }[] {
  const seen = new Set<string>();
  const out: { name: string }[] = [];
  for (const file of [...pending, ...contextFiles]) {
    if (seen.has(file.name)) continue;
    seen.add(file.name);
    out.push({ name: file.name });
  }
  return out;
}

export interface SessionController {
  session: SessionInfo | null;
  busy: boolean;
  error: string | null;
  /** Files attached before a conversation exists — shown immediately. */
  pending: PendingFile[];
  refresh: () => void;
  uploadFiles: (files: FileList | File[]) => Promise<void>;
  /**
   * Upload anything attached before the conversation existed into `chatId`, and
   * WAIT for it. Call this before starting a run so the run's context documents
   * include a file attached on the empty state — otherwise the turn starts
   * before the upload lands and the attachment is silently missing.
   */
  flushPending: (chatId: string) => Promise<void>;
  removeFile: (file: SessionFile) => Promise<void>;
  removePending: (name: string) => void;
}

export function useSession(chatId: string | null, refreshKey = 0): SessionController {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localKey, setLocalKey] = useState(0);
  const [pending, setPending] = useState<PendingFile[]>([]);
  const chatIdRef = useRef(chatId);
  chatIdRef.current = chatId;
  // Files attached before a conversation exists, flushed on the first reload.
  const pendingRef = useRef<File[]>([]);

  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    const id = chatIdRef.current;
    const list = Array.from(files);
    if (list.length === 0) return;
    // No conversation yet (empty state): hold the files and SHOW them right away,
    // so attaching before the first message is visible instead of silent. They
    // flush into the session folder once the first message creates the chat.
    if (!id) {
      for (const file of list) {
        if (file.size > SESSION_LIMITS.maxFileBytes) {
          const limit = Math.round(SESSION_LIMITS.maxFileBytes / 1024 / 1024);
          setError(`${file.name} exceeds ${limit}MB`);
          continue;
        }
        pendingRef.current.push(file);
        setPending((prev) => [...prev.filter((p) => p.name !== file.name), { name: file.name, bytes: file.size }]);
      }
      setError(null);
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

  const flushPending = useCallback(async (id: string) => {
    const queued = pendingRef.current;
    if (queued.length === 0) return;
    pendingRef.current = [];
    setPending([]);
    setBusy(true);
    try {
      for (const file of queued) {
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
        await flushPending(id);
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
  }, [flushPending]);
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

  const removePending = useCallback((name: string) => {
    pendingRef.current = pendingRef.current.filter((f) => f.name !== name);
    setPending((prev) => prev.filter((p) => p.name !== name));
  }, []);

  return { session, busy, error, pending, refresh, uploadFiles, flushPending, removeFile, removePending };
}
