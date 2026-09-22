// Shared (client + server) shapes for the per-conversation session workspace.
//
// Each chat conversation maps to a real folder on disk. Files the user adds as
// context and files the agent produces as output live there. This module is
// client-safe: it declares only the wire shapes, no `fs`.

export type SessionFileKind = "context" | "output";

export interface SessionFile {
  name: string;
  kind: SessionFileKind;
  bytes: number;
  /** ISO timestamp of last write. */
  updatedAt: string;
  /** True when the file's text could be extracted and used as run context. */
  textExtractable: boolean;
}

export interface SessionInfo {
  chatId: string;
  /** Absolute on-disk path, for display in the session bar. */
  path: string;
  files: SessionFile[];
  /**
   * Extracted characters across all *context* files — the amount of document
   * text actually available to inject into a run right now.
   */
  contextChars: number;
  /** The cap that `contextChars` is measured against. */
  contextLimitChars: number;
}

/** A document whose text is injected into the agent run as context. */
export interface RunDocument {
  name: string;
  text: string;
}

/**
 * A checkpoint: a restorable snapshot of one conversation's turns at a point in
 * time. Like an editor's save point — the user can roll the conversation back to
 * a known-good state before a change, and compare from there.
 */
export interface Checkpoint {
  id: string;
  chatId: string;
  /** Human label, e.g. "Before asking about AAPL". */
  label: string;
  /** ISO timestamp when it was taken. */
  createdAt: string;
  /** Number of turns captured (for the UI, without loading the payload). */
  messageCount: number;
  /** Bytes of the snapshot payload. */
  bytes: number;
}

/** The checkpoint payload — the conversation state to restore. */
export interface CheckpointSnapshot {
  chatId: string;
  label: string;
  createdAt: string;
  messages: Array<{ id: string; role: string; content: string }>;
}

/** Limits, shared so the UI can warn before a request is rejected. */
export const SESSION_LIMITS = {
  /** Max size of a single uploaded file. */
  maxFileBytes: 8 * 1024 * 1024,
  /** Max characters of any one document injected into a run. */
  maxDocChars: 20_000,
  /** Max combined characters of all injected documents. */
  maxTotalDocChars: 60_000,
  /** Max number of context files per conversation. */
  maxContextFiles: 20,
} as const;
