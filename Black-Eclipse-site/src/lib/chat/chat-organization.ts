import type { Message } from '@/types/chat';

/**
 * Chat-history organization — the "pro" data layer.
 *
 * The sidebar's conversations are client-side and persisted in localStorage
 * (there is no Prisma chat model). This module owns the shape of a stored
 * conversation plus everything layered on top — folders (nested), tags, colors,
 * pinning, archive and trash — and the pure view logic (filter / ranked search /
 * sort / tree-group) the sidebar renders. Storage-agnostic so it unit-tests in
 * the node environment.
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
  /** Free-form labels, normalised (trimmed, lower-cased, de-duplicated). */
  tags?: string[];
  /** When set, the chat lives in the Archive (epoch ms). */
  archivedAt?: number | null;
  /** When set, the chat lives in Trash and is hidden from every other view. */
  deletedAt?: number | null;
}

/** A user-created chat folder (nestable, orderable). */
export interface ChatFolder {
  id: string;
  name: string;
  color: string;
  collapsed?: boolean;
  /** Parent folder id for nesting, or null/absent at the root. */
  parentId?: string | null;
  /** Sort key among siblings. */
  order?: number;
}

export type ChatSortMode = 'recent' | 'created' | 'alpha';
/** Which slice of history a view shows. */
export type ChatScope = 'active' | 'archived' | 'trash';

/** One rendered group of the history list. `folder: null` is the "Unfiled" bucket. */
export interface ChatHistoryGroup {
  folder: ChatFolder | null;
  /** Nesting depth (0 = root) for indentation. */
  depth: number;
  conversations: Conversation[];
}

export interface ChatHistoryView {
  /** Pinned chats (always shown first, folder-agnostic; active scope only). */
  pinned: Conversation[];
  /** Folder groups (all folders, even empty ones) plus a trailing "Unfiled". */
  groups: ChatHistoryGroup[];
  /** Total conversations in the store (unfiltered). */
  total: number;
  /** Conversations matching the active query + scope + tag. */
  matches: number;
}

export interface SearchHit {
  conversation: Conversation;
  score: number;
  /** A short body excerpt around the first match, or null if only the title matched. */
  snippet: string | null;
}

/** A folder with its children resolved, for rendering. */
export interface ChatFolderNode {
  folder: ChatFolder;
  children: ChatFolderNode[];
  depth: number;
}

/** The folder/pin/tag/archive/trash actions the chat-history UI invokes. */
export interface ChatOrganizationApi {
  folders: ChatFolder[];
  load: () => void;
  createFolder: (name?: string) => string;
  renameFolder: (id: string, name: string) => void;
  deleteFolder: (id: string) => void;
  toggleFolder: (id: string) => void;
  setFolderColor: (id: string, color: string) => void;
  /** Reparent and/or reorder a folder among its siblings. */
  moveFolder: (id: string, parentId: string | null, beforeId: string | null) => void;
  moveConversation: (id: string, folderId: string | null) => void;
  setConversationColor: (id: string, color: string | null) => void;
  togglePin: (id: string) => void;
  renameConversation: (id: string, title: string) => void;
  addTag: (id: string, tag: string) => void;
  removeTag: (id: string, tag: string) => void;
  archive: (id: string) => void;
  unarchive: (id: string) => void;
  trash: (id: string) => void;
  restore: (id: string) => void;
  purge: (id: string) => void;
  emptyTrash: () => void;
  bulkMove: (ids: string[], folderId: string | null) => void;
  bulkArchive: (ids: string[]) => void;
  bulkUnarchive: (ids: string[]) => void;
  bulkTrash: (ids: string[]) => void;
  bulkRestore: (ids: string[]) => void;
  bulkPurge: (ids: string[]) => void;
  bulkPin: (ids: string[], pinned: boolean) => void;
  importFromText: (text: string) => { addedConversations: number; addedFolders: number; error?: string };
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

function finiteOrNull(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** Normalise a tag: trimmed, lower-cased; null for empties. */
export function normalizeTag(raw: string): string | null {
  const tag = raw.trim().toLowerCase();
  return tag ? tag : null;
}

function normalizeTags(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  for (const t of raw) {
    if (typeof t !== 'string') continue;
    const tag = normalizeTag(t);
    if (tag && !out.includes(tag)) out.push(tag);
  }
  return out;
}

/**
 * Coerce one persisted row into a Conversation, backfilling organization fields.
 * Returns null for rows too malformed to use.
 */
export function normalizeConversation(raw: unknown): Conversation | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.id !== 'string' || !raw.id) return null;
  const messages = Array.isArray(raw.messages) ? raw.messages.filter(isMessage) : [];
  const timestamp = finiteOrNull(raw.timestamp) ?? Date.now();
  return {
    id: raw.id,
    title: typeof raw.title === 'string' ? raw.title : '',
    messages,
    timestamp,
    createdAt: finiteOrNull(raw.createdAt) ?? timestamp,
    folderId: typeof raw.folderId === 'string' ? raw.folderId : null,
    color: typeof raw.color === 'string' ? raw.color : null,
    pinned: raw.pinned === true,
    tags: normalizeTags(raw.tags),
    archivedAt: finiteOrNull(raw.archivedAt),
    deletedAt: finiteOrNull(raw.deletedAt),
  };
}

/** Coerce a persisted conversation array, dropping unusable rows. */
export function normalizeConversations(raw: unknown): Conversation[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeConversation).filter((c): c is Conversation => c !== null);
}

function coerceFolder(raw: unknown): ChatFolder | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.id !== 'string' || !raw.id) return null;
  const name = typeof raw.name === 'string' && raw.name.trim() ? raw.name : 'Folder';
  const color = typeof raw.color === 'string' && raw.color ? raw.color : DEFAULT_FOLDER_COLOR;
  const folder: ChatFolder = { id: raw.id, name, color };
  if (raw.collapsed === true) folder.collapsed = true;
  if (typeof raw.parentId === 'string' && raw.parentId) folder.parentId = raw.parentId;
  const order = finiteOrNull(raw.order);
  if (order !== null) folder.order = order;
  return folder;
}

/** Coerce a persisted folder array, dropping unusable rows. */
export function normalizeFolders(raw: unknown): ChatFolder[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(coerceFolder).filter((f): f is ChatFolder => f !== null);
}

/** Read folders from storage, tolerating junk. */
export function loadFolders(storage: Pick<Storage, 'getItem'>): ChatFolder[] {
  try {
    const raw = storage.getItem(FOLDERS_STORAGE_KEY);
    if (!raw) return [];
    return normalizeFolders(JSON.parse(raw));
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

// ── Scope & tags ─────────────────────────────────────────────────────────────

/** True when a conversation belongs to the given scope. */
export function inScope(conv: Conversation, scope: ChatScope): boolean {
  if (scope === 'trash') return !!conv.deletedAt;
  if (conv.deletedAt) return false;
  if (scope === 'archived') return !!conv.archivedAt;
  return !conv.archivedAt;
}

/** Every distinct tag in use, sorted, from the given conversations. */
export function collectTags(convs: Conversation[]): string[] {
  const set = new Set<string>();
  for (const c of convs) for (const t of c.tags ?? []) set.add(t);
  return [...set].sort();
}

// ── Search ───────────────────────────────────────────────────────────────────

function tokenize(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

function buildSnippet(conv: Conversation, tokens: string[]): string | null {
  for (const m of conv.messages) {
    if (typeof m.content !== 'string') continue;
    const lower = m.content.toLowerCase();
    const idx = tokens.map((t) => lower.indexOf(t)).filter((i) => i >= 0).sort((a, b) => a - b)[0];
    if (idx === undefined) continue;
    const start = Math.max(0, idx - 30);
    const end = Math.min(m.content.length, idx + 70);
    const text = m.content.slice(start, end).replace(/\s+/g, ' ').trim();
    return `${start > 0 ? '…' : ''}${text}${end < m.content.length ? '…' : ''}`;
  }
  return null;
}

/**
 * Score a conversation against a query. Every token must appear somewhere
 * (AND semantics). Title hits weigh far more than body hits; a title prefix
 * bonus ranks the most relevant first. Returns null when the chat does not match.
 */
export function scoreConversation(conv: Conversation, query: string): SearchHit | null {
  const tokens = tokenize(query);
  if (!tokens.length) return { conversation: conv, score: 0, snippet: null };
  const title = conv.title.toLowerCase();
  const tagText = (conv.tags ?? []).join(' ');
  const body = conv.messages.map((m) => (typeof m.content === 'string' ? m.content.toLowerCase() : '')).join('\n');
  let score = 0;
  for (const tok of tokens) {
    const inTitle = title.includes(tok);
    const inTag = tagText.includes(tok);
    const inBody = body.includes(tok);
    if (!inTitle && !inTag && !inBody) return null;
    if (inTitle) score += 6;
    if (inTag) score += 3;
    if (inBody) score += 1;
    if (title.startsWith(tok)) score += 4;
  }
  return { conversation: conv, score, snippet: buildSnippet(conv, tokens) };
}

/** Ranked search over a set of conversations (score desc, then recency). */
export function searchConversations(convs: Conversation[], query: string): SearchHit[] {
  return convs
    .map((c) => scoreConversation(c, query))
    .filter((h): h is SearchHit => h !== null)
    .sort((a, b) => b.score - a.score || b.conversation.timestamp - a.conversation.timestamp);
}

/** Legacy predicate kept for callers/tests: title or body contains the query. */
export function matchesQuery(conv: Conversation, query: string): boolean {
  return scoreConversation(conv, query) !== null;
}

/** Filter by a free-text query (ranked order preserved). */
export function filterConversations(convs: Conversation[], query: string): Conversation[] {
  if (!query.trim()) return convs;
  return searchConversations(convs, query).map((h) => h.conversation);
}

// ── Sort ─────────────────────────────────────────────────────────────────────

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

// ── Folder tree ──────────────────────────────────────────────────────────────

function byOrder(a: ChatFolder, b: ChatFolder): number {
  return (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name);
}

/** True when making `id` a child of `parentId` would create a cycle. */
export function wouldCycle(folders: ChatFolder[], id: string, parentId: string | null): boolean {
  if (!parentId) return false;
  if (parentId === id) return true;
  const byId = new Map(folders.map((f) => [f.id, f]));
  let cur: string | null = parentId;
  const seen = new Set<string>();
  while (cur) {
    if (cur === id) return true;
    if (seen.has(cur)) return true;
    seen.add(cur);
    cur = byId.get(cur)?.parentId ?? null;
  }
  return false;
}

/** Build the folder forest (roots + nested children), cycle-safe. */
export function buildFolderTree(folders: ChatFolder[]): ChatFolderNode[] {
  const byId = new Map(folders.map((f) => [f.id, f]));
  const children = new Map<string, ChatFolder[]>();
  const roots: ChatFolder[] = [];
  for (const f of folders) {
    const pid = f.parentId ?? null;
    if (pid && pid !== f.id && byId.has(pid) && !wouldCycle(folders, f.id, pid)) {
      const list = children.get(pid) ?? [];
      list.push(f);
      children.set(pid, list);
    } else {
      roots.push(f);
    }
  }
  roots.sort(byOrder);
  const build = (folder: ChatFolder, depth: number): ChatFolderNode => {
    const kids = (children.get(folder.id) ?? []).slice().sort(byOrder);
    return { folder, depth, children: kids.map((k) => build(k, depth + 1)) };
  };
  return roots.map((r) => build(r, 0));
}

/** Pre-order flatten of the forest (parents before their children). */
export function flattenFolderTree(nodes: ChatFolderNode[]): ChatFolderNode[] {
  const out: ChatFolderNode[] = [];
  const walk = (n: ChatFolderNode) => {
    out.push(n);
    n.children.forEach(walk);
  };
  nodes.forEach(walk);
  return out;
}

/** Every folder id in `id`'s subtree (including itself). */
export function folderSubtreeIds(folders: ChatFolder[], id: string): string[] {
  const out = [id];
  const stack = [id];
  while (stack.length) {
    const cur = stack.pop()!;
    for (const f of folders) {
      if ((f.parentId ?? null) === cur) {
        out.push(f.id);
        stack.push(f.id);
      }
    }
  }
  return out;
}

// ── Grouping & the rendered view ─────────────────────────────────────────────

/**
 * Bucket conversations by folder following the folder forest order. Every folder
 * is included (even empty ones) with its nesting depth; the "Unfiled" bucket
 * (folder: null) is appended last only when it has members.
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
  const tree = flattenFolderTree(buildFolderTree(folders));
  const groups: ChatHistoryGroup[] = tree.map((node) => ({
    folder: node.folder,
    depth: node.depth,
    conversations: byFolder.get(node.folder.id) ?? [],
  }));
  if (unfiled.length) groups.push({ folder: null, depth: 0, conversations: unfiled });
  return groups;
}

/**
 * The full rendered view: scope + tag pre-filter, then either a flat ranked
 * search result, a flat archive/trash list, or the pinned + folder-tree layout.
 */
export function buildChatHistoryView(
  convs: Conversation[],
  folders: ChatFolder[],
  opts: { query?: string; sort?: ChatSortMode; scope?: ChatScope; tag?: string | null } = {},
): ChatHistoryView {
  const scope = opts.scope ?? 'active';
  const tag = opts.tag ?? null;
  const query = (opts.query ?? '').trim();
  const scoped = convs.filter((c) => inScope(c, scope) && (!tag || (c.tags ?? []).includes(tag)));

  if (query) {
    const hits = searchConversations(scoped, query);
    return {
      pinned: [],
      groups: [{ folder: null, depth: 0, conversations: hits.map((h) => h.conversation) }],
      total: convs.length,
      matches: hits.length,
    };
  }

  const sorted = sortConversations(scoped, opts.sort ?? 'recent');
  if (scope !== 'active') {
    return { pinned: [], groups: [{ folder: null, depth: 0, conversations: sorted }], total: convs.length, matches: sorted.length };
  }

  const pinned = sorted.filter((c) => c.pinned);
  const rest = sorted.filter((c) => !c.pinned);
  return { pinned, groups: groupConversations(rest, folders), total: convs.length, matches: sorted.length };
}
