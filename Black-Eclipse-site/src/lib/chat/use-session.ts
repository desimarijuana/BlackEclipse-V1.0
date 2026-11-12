'use client';

// Client hook owning a conversation's session workspace: the loaded listing,
// uploads, deletes, and a refresh trigger. Shared so the composer's Plus button
// and the session bar act on the same state instead of each fetching their own.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deleteSessionFile,
  fetchSession,
  sessionFileUrl,
  uploadSessionFile,
} from './session-client';
import { SESSION_LIMITS, type FileProvenance, type SessionFile, type SessionInfo } from './session-types';
import { claimPastes, pastedTextName } from './paste';
import type { FileRef, PickedFile } from './file-sources';
import { readWorkspaceFile } from '@/lib/harness/clients/code-browser';

export interface PendingFile {
  name: string;
  bytes: number;
  meta?: FileProvenance;
}

/** Normalize any accepted upload input into `PickedFile`s with provenance. */
export function toPickedFiles(input: FileList | File[] | PickedFile[]): PickedFile[] {
  return Array.from(input as ArrayLike<File | PickedFile>).map((item) => {
    if (item && typeof item === 'object' && 'file' in item) {
      const picked = item as PickedFile;
      return { file: picked.file, meta: picked.meta ?? { origin: 'upload' } };
    }
    return { file: item as File, meta: { origin: 'upload' } };
  });
}

/** A pasted document to show on the user turn that first used it. */
export interface PastedAttachment {
  name: string;
  chars: number;
  preview: string;
}

/** How much of a paste is kept for the transcript card (display only). */
export const PASTED_PREVIEW_CHARS = 240;

/**
 * The visible attachment chips: pending files first, then the session's saved
 * context files, de-duplicated by name (a file shown as pending must not appear
 * twice once it lands in the session). Pure, so the display rule is testable.
 */
export function mergeAttachmentChips<T extends { name: string }>(
  pending: T[],
  contextFiles: T[],
): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const file of [...pending, ...contextFiles]) {
    if (seen.has(file.name)) continue;
    seen.add(file.name);
    out.push(file);
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
  uploadFiles: (files: FileList | File[] | PickedFile[]) => Promise<void>;
  /**
   * Attach one PROJECT file by relative path: the runtime reads it (confined to
   * the approved root) and the text is uploaded as context with `project`
   * provenance. Used by the file picker and the composer's `@` palette.
   */
  attachProjectFile: (ref: FileRef) => Promise<void>;
  /**
   * Attach PASTED TEXT as a context document, exactly like an uploaded file
   * (same session folder, same chip, same extraction into the run). Used when a
   * paste is too big to belong in the composer.
   */
  attachText: (text: string, reservedNames?: Iterable<string>) => Promise<void>;
  /**
   * Open an attachment for READING. A pasted text opens the in-memory preview
   * (it is not read back from disk); any other document opens the session file.
   */
  openAttachment: (name: string) => void;
  /** The pasted text being previewed, or null. */
  preview: { name: string; text: string } | null;
  closePreview: () => void;
  /**
   * Claim the pasted documents added since the last send. They STAY attachments
   * (the run keeps reading them as context); the claim only marks that the next
   * user turn should show them, so an old paste is never re-labelled on every
   * later message.
   */
  claimPastedAttachments: () => PastedAttachment[];
  /** Wait for paste uploads already in flight, so the next run sees them. */
  flushAttachments: () => Promise<void>;
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
  // Pasted text, kept in memory under its attachment name so it can be read
  // back (a preview) and shown on the turn that sent it without a disk
  // round-trip. `claimed` records which pastes already belong to a user turn.
  const pastedTextsRef = useRef(new Map<string, string>());
  const claimedPastesRef = useRef(new Set<string>());
  const [preview, setPreview] = useState<{ name: string; text: string } | null>(null);
  const chatIdRef = useRef(chatId);
  chatIdRef.current = chatId;
  // A paste belongs to the conversation it was attached in. Switching chats
  // must not let an unclaimed paste from the old thread appear on a new turn.
  useEffect(() => {
    pastedTextsRef.current.clear();
    claimedPastesRef.current.clear();
    setPreview(null);
  }, [chatId]);
  // Files attached before a conversation exists, flushed on the first reload.
  const pendingRef = useRef<PickedFile[]>([]);
  // Uploads started by a paste. Sending can happen before the round-trip ends.
  const attachingRef = useRef(new Set<Promise<void>>());

  const uploadFiles = useCallback(async (input: FileList | File[] | PickedFile[]) => {
    const id = chatIdRef.current;
    const list = toPickedFiles(input);
    if (list.length === 0) return;
    // No conversation yet (empty state): hold the files and SHOW them right away,
    // so attaching before the first message is visible instead of silent. They
    // flush into the session folder once the first message creates the chat.
    if (!id) {
      for (const { file, meta } of list) {
        if (file.size > SESSION_LIMITS.maxFileBytes) {
          const limit = Math.round(SESSION_LIMITS.maxFileBytes / 1024 / 1024);
          setError(`${file.name} exceeds ${limit}MB`);
          continue;
        }
        pendingRef.current.push({ file, meta });
        setPending((prev) => [
          ...prev.filter((p) => p.name !== file.name),
          { name: file.name, bytes: file.size, meta },
        ]);
      }
      setError(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      for (const { file, meta } of list) {
        if (file.size > SESSION_LIMITS.maxFileBytes) {
          throw new Error(
            `${file.name} exceeds ${Math.round(SESSION_LIMITS.maxFileBytes / 1024 / 1024)}MB`
          );
        }
        const bytes = new Uint8Array(await file.arrayBuffer());
        await uploadSessionFile(id, 'context', file.name, bytes, meta);
      }
      setLocalKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }, []);

  /**
   * Attach a project file by relative path. The runtime reads it through the
   * SAME confinement the editor and tools use, so a path outside the approved
   * root is refused rather than guessed at.
   */
  const attachProjectFile = useCallback(async (ref: FileRef) => {
    try {
      const result = await readWorkspaceFile(ref.path, ref.rootId ?? null);
      const meta: FileProvenance = {
        origin: 'project',
        sourcePath: result.path || ref.path,
        rootId: ref.rootId ?? null,
        rootLabel: ref.rootLabel ?? null,
      };
      const name = ref.name || result.path.split('/').pop() || 'file';
      const file = new File([result.content], name, { type: 'text/plain' });
      await uploadFiles([{ file, meta }]);
      if (result.redacted) setError(`${name} contained secrets; they were redacted before attaching.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not attach that file');
    }
  }, [uploadFiles]);

  /**
   * Attach pasted text as a context document. It goes through the SAME upload
   * path as a file, so it gets a chip, lands in the session folder, and is
   * extracted into every run exactly like an attached document.
   */
  const attachText = useCallback(async (text: string, reservedNames?: Iterable<string>) => {
    const taken = [
      ...(reservedNames ?? []),
      ...pastedTextsRef.current.keys(),
      ...pendingRef.current.map((f) => f.file.name),
      ...(session?.files ?? []).map((f) => f.name),
    ];
    const name = pastedTextName(taken);
    pastedTextsRef.current.set(name, text);
    claimedPastesRef.current.delete(name);
    const file = new File([text], name, { type: 'text/plain' });
    const task = uploadFiles([{ file, meta: { origin: 'paste' } }]);
    attachingRef.current.add(task);
    try {
      await task;
    } finally {
      attachingRef.current.delete(task);
    }
  }, [uploadFiles, session]);

  const flushAttachments = useCallback(async () => {
    if (attachingRef.current.size === 0) return;
    await Promise.allSettled([...attachingRef.current]);
  }, []);

  const openAttachment = useCallback((name: string) => {
    const text = pastedTextsRef.current.get(name);
    if (text !== undefined) {
      setPreview({ name, text });
      return;
    }
    const id = chatIdRef.current;
    if (id) window.open(sessionFileUrl(id, 'context', name), '_blank', 'noopener');
  }, []);

  const closePreview = useCallback(() => setPreview(null), []);

  const claimPastedAttachments = useCallback((): PastedAttachment[] => {
    return claimPastes(pastedTextsRef.current, claimedPastesRef.current).map(({ name, text }) => ({
      name,
      chars: text.length,
      preview: text.slice(0, PASTED_PREVIEW_CHARS),
    }));
  }, []);

  const flushPending = useCallback(async (id: string) => {
    const queued = pendingRef.current;
    if (queued.length === 0) return;
    pendingRef.current = [];
    setPending([]);
    setBusy(true);
    try {
      for (const { file, meta } of queued) {
        const bytes = new Uint8Array(await file.arrayBuffer());
        await uploadSessionFile(id, 'context', file.name, bytes, meta);
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
      pastedTextsRef.current.delete(file.name);
      claimedPastesRef.current.delete(file.name);
      if (preview?.name === file.name) setPreview(null);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  }, [preview, refresh]);

  const removePending = useCallback((name: string) => {
    pendingRef.current = pendingRef.current.filter((f) => f.file.name !== name);
    setPending((prev) => prev.filter((p) => p.name !== name));
    pastedTextsRef.current.delete(name);
    claimedPastesRef.current.delete(name);
    if (preview?.name === name) setPreview(null);
  }, [preview]);

  return { session, busy, error, pending, refresh, uploadFiles, attachProjectFile, attachText, openAttachment, preview, closePreview, claimPastedAttachments, flushAttachments, flushPending, removeFile, removePending };
}
