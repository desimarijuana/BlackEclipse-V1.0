import {
  normalizeConversations,
  normalizeFolders,
  type ChatFolder,
  type Conversation,
} from './chat-organization';

/**
 * Portable chat-history export/import (JSON).
 *
 * Pure and storage-agnostic so the format is a contract: `kind` + `version`
 * gate compatibility, and import is defensive — malformed entries are dropped by
 * the shared normalizers rather than corrupting the store. Merge is id-based and
 * non-destructive: an incoming record whose id already exists is skipped.
 */

export const CHAT_EXPORT_KIND = 'black-eclipse.chat-history';
export const CHAT_EXPORT_VERSION = 1;

export interface ChatExport {
  kind: typeof CHAT_EXPORT_KIND;
  version: number;
  exportedAt: string;
  conversations: Conversation[];
  folders: ChatFolder[];
}

/** Build the export payload from the live store. */
export function buildExport(
  conversations: Conversation[],
  folders: ChatFolder[],
  now: number = Date.now(),
): ChatExport {
  return {
    kind: CHAT_EXPORT_KIND,
    version: CHAT_EXPORT_VERSION,
    exportedAt: new Date(now).toISOString(),
    conversations,
    folders,
  };
}

/** Pretty-printed JSON string ready for download. */
export function serializeExport(conversations: Conversation[], folders: ChatFolder[], now?: number): string {
  return JSON.stringify(buildExport(conversations, folders, now), null, 2);
}

export interface ParsedImport {
  conversations: Conversation[];
  folders: ChatFolder[];
}

/**
 * Parse an imported JSON document. Accepts either the versioned envelope or a
 * bare `{ conversations, folders }`. Throws when the shape is unusable.
 */
export function parseImport(text: string): ParsedImport {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new Error('Not valid JSON');
  }
  if (typeof raw !== 'object' || raw === null) throw new Error('Unrecognised chat export');
  const obj = raw as Record<string, unknown>;
  if (obj.kind !== undefined && obj.kind !== CHAT_EXPORT_KIND) {
    throw new Error('Not a BlackEclipse chat export');
  }
  const conversations = normalizeConversations(obj.conversations);
  const folders = normalizeFolders(obj.folders);
  if (!conversations.length && !folders.length) throw new Error('Nothing to import');
  return { conversations, folders };
}

export interface MergeResult {
  conversations: Conversation[];
  folders: ChatFolder[];
  addedConversations: number;
  addedFolders: number;
}

/**
 * Merge an import into the existing store. Existing records always win on an id
 * collision (import is additive); imported chats keep their folderId, which
 * resolves to the existing folder of the same id when present.
 */
export function mergeImport(
  existingConversations: Conversation[],
  existingFolders: ChatFolder[],
  incoming: ParsedImport,
): MergeResult {
  const convIds = new Set(existingConversations.map((c) => c.id));
  const folderIds = new Set(existingFolders.map((f) => f.id));
  const addedConv = incoming.conversations.filter((c) => !convIds.has(c.id));
  const addedFolder = incoming.folders.filter((f) => !folderIds.has(f.id));
  return {
    conversations: [...addedConv, ...existingConversations],
    folders: [...existingFolders, ...addedFolder],
    addedConversations: addedConv.length,
    addedFolders: addedFolder.length,
  };
}
