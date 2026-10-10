import type { Message } from '@/types/chat';

/**
 * Chat-history organization.
 *
 * The sidebar's "recent chats" list is client-side and persisted in
 * localStorage (there is no Prisma chat model). This module owns the shape of a
 * stored conversation plus the folders/colors/pinning metadata layered on top,
 * and the pure view logic (filter / sort / group) the sidebar panel renders.
 *
 * Everything here is storage-agnostic (callers pass a `Storage`-like object) so
 * it stays unit-testable in the node test environment.
 */

/** A single saved conversation. Extra fields are optional so legacy rows load. */
export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  /** Last-activity stamp (epoch ms). Updated on every append. */
  timestamp: number;
  /** Creation stamp (epoch ms). Backfilled from `timestamp` on legacy rows. */
  createdAt?: number;
  /** Owning folder id, or null/absent when unfiled. */
  folderId?: string | null;
  /** User-assigned accent color (hex), or null for the default. */
  color?: string | null;
  /** Pinned chats surface in a dedicated section above folders. */
  pinned?: boolean;
}

/** A user-created chat folder. */
export interface ChatFolder {
  id: string;
  name: string;
  /** Accent color (hex) shown as the folder dot. */
  color: string;
  collapsed?: boolean;
}

export type ChatSortMode = 'recent' | 'created' | 'alpha';

/**
 * The folder/pin/color/rename/move actions the chat-history UI invokes. Bundled
 * into one object so the sidebar and its panel take a single prop instead of a
 * dozen callbacks.
 */
export interface ChatOrganizationApi {
  folders: ChatFolder[];
  load: () => void;
  createFolder: () => void;
  renameFolder: (id: string, name: string) => void;
  deleteFolder: (id: string) => void;
  toggleFolder: (id: string) => void;
  setFolderColor: (id: string, color: string) => void;
  moveConversation: (id: string, folderId: string | null) => void;
  setConversationColor: (id: string, color: string | null) => void;
  togglePin: (id: string) => void;
  renameConversation: (id: string, title: string) => void;
}

/** One rendered group of the history list. `folder: null` is the "Unfiled" bucket. */
export interface ChatHistoryGroup {
  folder: ChatFolder | null;
  conversations: Conversation[];
}

export interface ChatHistoryView {
  /** Pinned chats (always shown first, folder-agnostic). */
  pinned: Conversation[];
  /** Folder groups (only non-empty ones). */
  groups: ChatHistoryGroup[];
  /** Total conversations considered (before filtering). */
  total: number;
  /** Conversations matching the active query. */
  matches: number;
}

/** localStorage keys. `chats_guest` is the pre-existing conversation store. */
export const CONVERSATIONS_STORAGE_KEY = 'chats_guest';
export const FOLDERS_STORAGE_KEY = 'chat_folders_v1';

/** Accent palette shared by folders and individual chats. */
export const CHAT_COLORS = [
  { id: 'slate', value: '#64748b' },
  { id: 'red', value: '#ef4444' },
  { id: 'orange', value: '#f97316' },
  { id: 'amber', value: '#f59e0b' },
  { id: 'emerald', value: '#10b981' },
  { id: 'cyan', value: '#06b6d4' },
  { id: 'blue', value: '#3b82f6' },
  { id: 'violet', value: '#8b5cf6' },
  { id: 'pink', value: '#ec4899' },
] as const;

export type ChatColorId = (typeof CHAT_COLORS)[number]['id'];

export const DEFAULT_FOLDER_COLOR = CHAT_COLORS[0].value;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}

function isMessage(v: unknown): v is Message {
  return isRecord(v) && typeof v.id === 'string' && (v.role === 'user' || v.role === 'assistant');
}

/**
 * Coerce one persisted row into a Conversation, backfilling organization fields.
 * Returns null for rows too malformed to use.
 */
export function normalizeConversation(raw: unknown): Conversation | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.id !== 'string' || !raw.id) return null;
  const messages = Array.isArray(raw.messages) ? raw.messages.filter(isMessage) : [];
  const timestamp = typeof raw.timestamp === 'number' && Number.isFinite(raw.timestamp) ? raw.timestamp : Date.now();
  return {
    id: raw.id,
    title: typeof raw.title === 'string' ? raw.title : '',
    messages,
    timestamp,
    createdAt: typeof raw.createdAt === 'number' && Number.isFinite(raw.createdAt) ? raw.createdAt : timestamp,
    folderId: typeof raw.folderId === 'string' ? raw.folderId : null,
    color: typeof raw.color === 'string' ? raw.color : null,
    pinned: raw.pinned === true,
  };
}

/** Coerce a persisted conversation array, dropping unusable rows. */
export function normalizeConversations(raw: unknown): Conversation[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeConversation).filter((c): c is Conversation => c !== null);
}

/** True when a message body or title matches the (case-insensitive) query. */
export function matchesQuery(conv: Conversation, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (conv.title.toLowerCase().includes(q)) return true;
  return conv.messages.some((m) => typeof m.content === 'string' && m.content.toLowerCase().includes(q));
}

/** Filter conversations by a free-text query across titles and message bodies. */
export function filterConversations(convs: Conversation[], query: string): Conversation[] {
  const q = query.trim();
  if (!q) return convs;
  return convs.filter((c) => matchesQuery(c, q));
}

function sortKey(conv: Conversation, mode: ChatSortMode): number {
  if (mode === 'created') return conv.createdAt ?? conv.timestamp;
  return conv.timestamp;
}

/** Sort pinned first, then by the chosen key descending (alpha is ascending). */
export function sortConversations(convs: Conversation[], mode: ChatSortMode): Conversation[] {
  return [...convs].sort((a, b) => {
    if (!!a.pinned !== !!b.pinned) return a.pinned ? -1 : 1;
    if (mode === 'alpha') return a.title.localeCompare(b.title);
    return sortKey(b, mode) - sortKey(a, mode);
  });
}

/**
 * Bucket conversations by folder, preserving folder order. Every folder is
 * included (even empty ones, so a freshly created folder is visible), and the
 * "Unfiled" bucket (folder: null) is appended last only when it has members.
 */
export function groupConversations(convs: Conversation[], folders: ChatFolder[]): ChatHistoryGroup[] {
  const byFolder = new Map<string, Conversation[]>();
  const unfiled: Conversation[] = [];
  const known = new Set(folders.map((f) => f.id));
  for (const c of convs) {
    const fid = c.folderId;
    if (fid && known.has(fid)) {
      const list = byFolder.get(fid) ?? [];
      list.push(c);
      byFolder.set(fid, list);
    } else {
      unfiled.push(c);
    }
  }
  const groups: ChatHistoryGroup[] = folders.map((folder) => ({
    folder,
    conversations: byFolder.get(folder.id) ?? [],
  }));
  if (unfiled.length) groups.push({ folder: null, conversations: unfiled });
  return groups;
}

/**
 * The full rendered view: search, then split into a pinned section plus folder
 * groups. While searching, results are flattened into a single unfiled group so
 * matching across folders reads as one list.
 */
export function buildChatHistoryView(
  convs: Conversation[],
  folders: ChatFolder[],
  opts: { query?: string; sort?: ChatSortMode } = {},
): ChatHistoryView {
  const query = opts.query ?? '';
  const sort = opts.sort ?? 'recent';
  const filtered = filterConversations(convs, query);
  const sorted = sortConversations(filtered, sort);
  if (query.trim()) {
    return { pinned: [], groups: [{ folder: null, conversations: sorted }], total: convs.length, matches: sorted.length };
  }
  const pinned = sorted.filter((c) => c.pinned);
  const rest = sorted.filter((c) => !c.pinned);
  return { pinned, groups: groupConversations(rest, folders), total: convs.length, matches: sorted.length };
}

function coerceFolder(raw: unknown): ChatFolder | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.id !== 'string' || !raw.id) return null;
  const name = typeof raw.name === 'string' && raw.name.trim() ? raw.name : 'Folder';
  const color = typeof raw.color === 'string' && raw.color ? raw.color : DEFAULT_FOLDER_COLOR;
  const folder: ChatFolder = { id: raw.id, name, color };
  if (raw.collapsed === true) folder.collapsed = true;
  return folder;
}

/** Read folders from storage, tolerating junk. */
export function loadFolders(storage: Pick<Storage, 'getItem'>): ChatFolder[] {
  try {
    const raw = storage.getItem(FOLDERS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(coerceFolder).filter((f): f is ChatFolder => f !== null);
  } catch {
    return [];
  }
}

/** Persist folders to storage. */
export function saveFolders(storage: Pick<Storage, 'setItem'>, folders: ChatFolder[]): void {
  try {
    storage.setItem(FOLDERS_STORAGE_KEY, JSON.stringify(folders));
  } catch {
    /* quota or private-mode failure: organization is best-effort */
  }
}
