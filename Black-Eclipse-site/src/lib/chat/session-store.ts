// SERVER-ONLY: per-conversation session workspace on disk.
//
// Layout (root is gitignored — it holds user uploads and agent output):
//
//   <repo>/.black-eclipse/sessions/<chatId>/
//     context/   files the user added as agent context
//     output/    files the agent produced
//
// The chat id comes from the client and is used as a path segment, so it is
// strictly validated before any filesystem call: only a safe character class,
// no dots/slashes, bounded length. This is the one place untrusted input
// reaches `fs`, so the guard is duplicated in every entry point.

import { promises as fs } from "node:fs";
import path from "node:path";
import type { Message } from "@/types/chat";
import type { ConversationFork } from "./chat-organization";
import { extractText, extractDocumentText, isTextExtractable } from "./extract";
import {
  SESSION_LIMITS,
  type FileProvenance,
  type SessionFile,
  type SessionFileKind,
  type SessionInfo,
} from "./session-types";

const CHAT_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

// listTranscripts() reads + parses EVERY stored transcript file, and the ChatBot
// hydrates from it on every app boot. Re-reading the whole sessions tree each
// load made boot O(conversations) — 126 files / ~5MB took seconds and competed
// with the first page's own requests. Cache the parsed list in-process and drop
// it on any write/delete here; a short TTL covers edits from outside this
// process.
const TRANSCRIPT_LIST_TTL_MS = 15_000;
let transcriptListCache: { at: number; data: StoredTranscript[] } | null = null;
function invalidateTranscriptList(): void {
  transcriptListCache = null;
}

export class SessionError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = "SessionError";
    this.code = code;
  }
}

function assertChatId(chatId: string): string {
  if (!CHAT_ID_RE.test(chatId)) {
    throw new SessionError("INVALID_CHAT_ID", "Invalid conversation id");
  }
  return chatId;
}

// A file name is accepted if it is SAFE, not if it is plain ASCII. An allowlist
// of `[A-Za-z0-9._ -]` rejected extremely common real names — `notes(1).md`,
// `résumé.pdf`, `Q3 [final].xlsx`, `R&D.csv` — so "attach a file" failed for most
// files a person actually picks. This is a DENYLIST of the characters that are
// unsafe or invalid: path separators, NUL/control chars, and the characters
// Windows forbids in a name. Everything else (Unicode letters, spaces, and
// ordinary punctuation) is allowed.
const UNSAFE_NAME_CHARS_RE = /[\/\\\x00-\x1f<>:"|?*]/;
const WINDOWS_RESERVED_RE = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i;
const MAX_NAME_CHARS = 160;

/** Reject traversal, separators, control characters and Windows-reserved names. */
function assertSafeName(name: string): string {
  const trimmed = name.trim();
  if (!trimmed || trimmed.length > MAX_NAME_CHARS) {
    throw new SessionError("INVALID_FILE_NAME", "Invalid file name");
  }
  if (trimmed === "." || trimmed === ".." || trimmed.startsWith(".")) {
    throw new SessionError("INVALID_FILE_NAME", "Invalid file name");
  }
  if (UNSAFE_NAME_CHARS_RE.test(trimmed) || WINDOWS_RESERVED_RE.test(trimmed)) {
    throw new SessionError("INVALID_FILE_NAME", "Invalid file name");
  }
  // A name must not be only dots/spaces.
  if (/^[.\s]+$/.test(trimmed)) {
    throw new SessionError("INVALID_FILE_NAME", "Invalid file name");
  }
  return trimmed;
}

export function sessionsRoot(): string {
  const override = process.env.BLACK_ECLIPSE_SESSION_ROOT;
  if (override) return path.resolve(override);
  // process.cwd() is Black-Eclipse-site when the app runs.
  return path.resolve(process.cwd(), ".black-eclipse", "sessions");
}

export function sessionDir(chatId: string): string {
  const root = sessionsRoot();
  const dir = path.resolve(root, assertChatId(chatId));
  // Belt-and-braces: the resolved dir must stay inside the root.
  if (dir !== root && !dir.startsWith(root + path.sep)) {
    throw new SessionError("INVALID_CHAT_ID", "Invalid conversation id");
  }
  return dir;
}

function kindDir(chatId: string, kind: SessionFileKind): string {
  return path.join(sessionDir(chatId), kind === "context" ? "context" : "output");
}

/** Resolve a file inside a session, rejecting any path escape. */
function resolveFile(chatId: string, kind: SessionFileKind, name: string): string {
  const dir = kindDir(chatId, kind);
  const full = path.resolve(dir, assertSafeName(name));
  if (!full.startsWith(dir + path.sep)) {
    throw new SessionError("INVALID_FILE_NAME", "Invalid file name");
  }
  return full;
}

async function ensureSessionDirs(chatId: string): Promise<string> {
  const dir = sessionDir(chatId);
  await fs.mkdir(path.join(dir, "context"), { recursive: true });
  await fs.mkdir(path.join(dir, "output"), { recursive: true });
  return dir;
}

async function listKind(chatId: string, kind: SessionFileKind): Promise<SessionFile[]> {
  const dir = kindDir(chatId, kind);
  let entries: import("node:fs").Dirent[];
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  // Provenance is stored beside the files (never inside the bytes). A missing or
  // unreadable sidecar simply means "no provenance yet" — the file still lists.
  const meta = kind === "context" ? await readContextMeta(chatId) : {};
  const files: SessionFile[] = [];
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    try {
      const stat = await fs.stat(path.join(dir, entry.name));
      files.push({
        name: entry.name,
        kind,
        bytes: stat.size,
        updatedAt: stat.mtime.toISOString(),
        textExtractable: isTextExtractable(entry.name),
        ...(meta[entry.name] ?? {}),
      });
    } catch {
      // Vanished between readdir and stat — skip.
    }
  }
  return files.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
}

// ── Provenance sidecar ───────────────────────────────────────────────────────
// One small JSON map per conversation: file name → where it came from. It is
// deliberately separate from the file bytes so a file copied into the folder by
// hand still lists (with unknown origin) instead of failing.

const CONTEXT_META_FILE = "context-meta.json";

function contextMetaPath(chatId: string): string {
  return path.join(sessionDir(chatId), CONTEXT_META_FILE);
}

const ORIGINS = new Set<FileProvenance["origin"]>(["upload", "project", "paste"]);

function coerceProvenance(raw: unknown): FileProvenance | null {
  if (!raw || typeof raw !== "object") return null;
  const blob = raw as Record<string, unknown>;
  const origin = typeof blob.origin === "string" && ORIGINS.has(blob.origin as FileProvenance["origin"])
    ? (blob.origin as FileProvenance["origin"])
    : null;
  if (!origin) return null;
  return {
    origin,
    sourcePath: typeof blob.sourcePath === "string" ? blob.sourcePath : null,
    rootId: typeof blob.rootId === "string" ? blob.rootId : null,
    rootLabel: typeof blob.rootLabel === "string" ? blob.rootLabel : null,
  };
}

async function readContextMeta(chatId: string): Promise<Record<string, FileProvenance>> {
  try {
    const raw = await fs.readFile(contextMetaPath(chatId), "utf8");
    const parsed = JSON.parse(raw) as Record<string, unknown> | null;
    if (!parsed || typeof parsed !== "object") return {};
    const out: Record<string, FileProvenance> = {};
    for (const [name, value] of Object.entries(parsed)) {
      const meta = coerceProvenance(value);
      if (meta) out[name] = meta;
    }
    return out;
  } catch {
    return {};
  }
}

async function writeContextMeta(
  chatId: string,
  meta: Record<string, FileProvenance>,
): Promise<void> {
  await fs.writeFile(contextMetaPath(chatId), JSON.stringify(meta), "utf8");
}

async function setContextMeta(chatId: string, name: string, meta: FileProvenance | null): Promise<void> {
  const current = await readContextMeta(chatId);
  if (meta) current[name] = meta;
  else delete current[name];
  await writeContextMeta(chatId, current);
}

/**
 * Extracted characters available across the context files, capped the same way
 * a real run caps them (per-doc limit, then the combined limit). This is what
 * the UI reports as "context used" — a measurement, never an estimate: a file
 * whose text cannot be extracted contributes nothing.
 */
export async function measureContextChars(chatId: string): Promise<number> {
  const files = await listKind(chatId, "context");
  let total = 0;
  for (const file of files) {
    if (total >= SESSION_LIMITS.maxTotalDocChars) break;
    try {
      const bytes = await readSessionFile(chatId, "context", file.name);
      const result = await extractDocumentText(file.name, bytes);
      if (!result.ok || !result.text) continue;
      total += Math.min(result.text.length, SESSION_LIMITS.maxDocChars, SESSION_LIMITS.maxTotalDocChars - total);
    } catch {
      // Unreadable file — contributes nothing.
    }
  }
  return total;
}

/** Full session view for the UI (creates the folders on first look). */
export async function getSession(chatId: string): Promise<SessionInfo> {
  const dir = await ensureSessionDirs(chatId);
  const [context, output, contextChars] = await Promise.all([
    listKind(chatId, "context"),
    listKind(chatId, "output"),
    measureContextChars(chatId),
  ]);
  return {
    chatId,
    path: dir,
    files: [...context, ...output],
    contextChars,
    contextLimitChars: SESSION_LIMITS.maxTotalDocChars,
  };
}

export interface WriteFileOptions {
  name: string;
  bytes: Uint8Array;
  kind: SessionFileKind;
  /** Where the file came from (context files only; shown on the chip). */
  meta?: FileProvenance;
}

/** Write a file into a session (upload or agent output). Returns its metadata. */
export async function writeSessionFile(
  chatId: string,
  { name, bytes, kind, meta }: WriteFileOptions
): Promise<SessionFile> {
  if (bytes.byteLength > SESSION_LIMITS.maxFileBytes) {
    throw new SessionError(
      "FILE_TOO_LARGE",
      `File exceeds ${Math.round(SESSION_LIMITS.maxFileBytes / 1024 / 1024)}MB limit`
    );
  }
  const safeName = assertSafeName(name);
  await ensureSessionDirs(chatId);
  if (kind === "context") {
    const existing = await listKind(chatId, "context");
    if (!existing.some((f) => f.name === safeName) && existing.length >= SESSION_LIMITS.maxContextFiles) {
      throw new SessionError("TOO_MANY_FILES", `At most ${SESSION_LIMITS.maxContextFiles} context files`);
    }
  }
  const full = resolveFile(chatId, kind, safeName);
  await fs.writeFile(full, bytes);
  // Persist provenance after the bytes land, so a failed write never leaves a
  // stale description of a file that does not exist.
  if (kind === "context" && meta) {
    await setContextMeta(chatId, safeName, meta);
  }
  const stat = await fs.stat(full);
  return {
    // FileProvenance requires an origin. A context file with stored metadata
    // keeps its real provenance; anything else is a local upload.
    origin: kind === "context" && meta ? meta.origin : "upload",
    name: safeName,
    kind,
    bytes: stat.size,
    updatedAt: stat.mtime.toISOString(),
    textExtractable: isTextExtractable(safeName),
    ...(kind === "context" && meta ? meta : {}),
  };
}

export async function readSessionFile(chatId: string, kind: SessionFileKind, name: string): Promise<Buffer> {
  return fs.readFile(resolveFile(chatId, kind, name));
}

export async function deleteSessionFile(chatId: string, kind: SessionFileKind, name: string): Promise<void> {
  await fs.unlink(resolveFile(chatId, kind, name));
  if (kind === "context") await setContextMeta(chatId, assertSafeName(name), null);
}

/**
 * Copy a conversation's CONTEXT documents into another conversation.
 *
 * A forked chat is a real new conversation with its own session folder. Its
 * copied user turns still reference attachments by name, and the next run reads
 * context from the NEW folder — so without this, a fork would show attachments
 * that cannot be opened and would silently lose their context.
 *
 * Output files and checkpoints are intentionally NOT copied: they belong to the
 * original runs, and a fork starts with a clean checkpoint history. Individual
 * unreadable/unsafe names are skipped rather than failing the whole fork.
 */
export async function cloneSessionContext(fromChatId: string, toChatId: string): Promise<{ copied: number }> {
  assertChatId(fromChatId);
  assertChatId(toChatId);
  if (fromChatId === toChatId) return { copied: 0 };
  await ensureSessionDirs(toChatId);

  const sourceDir = kindDir(fromChatId, "context");
  let entries: import("node:fs").Dirent[];
  try {
    entries = await fs.readdir(sourceDir, { withFileTypes: true });
  } catch {
    return { copied: 0 };
  }

  const sourceMeta = await readContextMeta(fromChatId);
  const targetMeta: Record<string, FileProvenance> = {};
  let copied = 0;
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    if (copied >= SESSION_LIMITS.maxContextFiles) break;
    try {
      const safeName = assertSafeName(entry.name);
      await fs.copyFile(
        path.join(sourceDir, safeName),
        resolveFile(toChatId, "context", safeName),
      );
      if (sourceMeta[safeName]) targetMeta[safeName] = sourceMeta[safeName];
      copied += 1;
    } catch {
      // A vanished, unsafe or unreadable file is skipped.
    }
  }
  if (Object.keys(targetMeta).length > 0) {
    const current = await readContextMeta(toChatId);
    await writeContextMeta(toChatId, { ...current, ...targetMeta });
  }
  return { copied };
}

/**
 * Load every context file as text for prompt injection. Extraction failures
 * are skipped rather than failing the run, and the total is capped so a large
 * set of documents cannot blow the context window. A shortened document is
 * MARKED (`truncated` + `originalChars`) so the runtime states the limit in the
 * turn instead of answering from only the first part.
 */
// ── Per-chat project folder (Phase 23) ─────────────────────────────────────────
//
// Each conversation can be bound to ONE approved workspace root. The binding is
// an ID, never a path: the run route forwards the id and the Python runtime
// resolves it against TrustedRoot, so the browser cannot point a run at an
// arbitrary directory. Stored beside the transcript so it survives a restart.

const PROJECT_FILE = "project.json";

export interface SessionProject {
  chatId: string;
  workspaceRootId: string | null;
  workspacePath: string | null;
  updatedAt: number;
}

function projectPath(chatId: string): string {
  return path.join(sessionDir(chatId), PROJECT_FILE);
}

export async function readSessionProject(chatId: string): Promise<SessionProject | null> {
  // Validate OUTSIDE the try: a malformed id is a caller error, not "no binding".
  assertChatId(chatId);
  try {
    const raw = await fs.readFile(projectPath(chatId), "utf8");
    const parsed = JSON.parse(raw) as Partial<SessionProject> | null;
    if (!parsed || typeof parsed !== "object") return null;
    const workspaceRootId = typeof parsed.workspaceRootId === "string" && parsed.workspaceRootId
      ? parsed.workspaceRootId
      : null;
    const workspacePath = typeof parsed.workspacePath === "string" && parsed.workspacePath
      ? parsed.workspacePath
      : null;
    return {
      chatId,
      workspaceRootId,
      workspacePath,
      updatedAt: typeof parsed.updatedAt === "number" ? parsed.updatedAt : Date.now(),
    };
  } catch {
    return null;
  }
}

export async function writeSessionProject(
  chatId: string,
  project: { workspaceRootId: string | null; workspacePath: string | null },
): Promise<SessionProject> {
  await ensureSessionDirs(chatId);
  const stored: SessionProject = {
    chatId,
    workspaceRootId: project.workspaceRootId ?? null,
    workspacePath: project.workspacePath ?? null,
    updatedAt: Date.now(),
  };
  await fs.writeFile(projectPath(chatId), JSON.stringify(stored), "utf8");
  return stored;
}

/** The run-facing read: only the id, or undefined when no project is bound. */
export async function readSessionWorkspaceRootId(chatId: string): Promise<string | undefined> {
  const project = await readSessionProject(chatId);
  return project?.workspaceRootId ?? undefined;
}

// ── Conversation transcripts (server-side durability) ────────────────────────
//
// The transcript used to live ONLY in browser localStorage (keyed by origin), so
// closing the server, changing the app origin (http vs https, hostname vs IP) or
// clearing storage silently dropped every conversation. A copy now lives on disk
// beside the session's files, keyed by the same chatId, and the ChatBot tab
// hydrates from it on boot. localStorage stays as an instant cache; the server
// copy is what makes a conversation survive.

const TRANSCRIPT_FILE = "transcript.json";
// A bounded transcript: an extremely long chat cannot grow the file without
// limit. 400 turns is far beyond any real conversation.
const MAX_TRANSCRIPT_MESSAGES = 400;

export interface StoredTranscript {
  id: string;
  title: string;
  messages: Message[];
  timestamp: number;
  createdAt: number;
  /** Server write stamp (epoch ms); the hydration merge prefers the newer copy. */
  updatedAt: number;
  /** Set when this conversation was forked from another one. */
  forkedFrom?: ConversationFork;
  folderId?: string | null;
  color?: string | null;
  pinned?: boolean;
  tags?: string[];
  archivedAt?: number | null;
  deletedAt?: number | null;
}

function transcriptPath(chatId: string): string {
  return path.join(sessionDir(chatId), TRANSCRIPT_FILE);
}

/** Read one conversation's persisted transcript, or null when absent/unusable. */
export async function readTranscript(chatId: string): Promise<StoredTranscript | null> {
  try {
    const raw = await fs.readFile(transcriptPath(chatId), "utf8");
    const parsed = JSON.parse(raw) as Partial<StoredTranscript> | null;
    if (!parsed || typeof parsed !== "object") return null;
    if (typeof parsed.id !== "string" || !Array.isArray(parsed.messages)) return null;
    return parsed as StoredTranscript;
  } catch {
    return null;
  }
}

const TERMINAL_MESSAGE_STATUS = new Set(["completed", "error", "cancelled"]);

/**
 * Merge two copies of the same transcript. Transcripts are append-mostly, and
 * two tabs may save different halves; union by message id instead of letting
 * the last writer erase the other tab's turn. A terminal assistant message
 * always beats an empty streaming placeholder with the same id.
 */
function mergeStoredMessages(existing: Message[], incoming: Message[]): Message[] {
  const merged = [...existing];
  const index = new Map(merged.map((message, i) => [message.id, i] as const));
  for (const message of incoming) {
    const at = index.get(message.id);
    if (at === undefined) {
      index.set(message.id, merged.length);
      merged.push(message);
      continue;
    }
    const current = merged[at];
    const currentTerminal = TERMINAL_MESSAGE_STATUS.has(String(current.status ?? ""));
    const incomingTerminal = TERMINAL_MESSAGE_STATUS.has(String(message.status ?? ""));
    if (incomingTerminal && !currentTerminal) merged[at] = message;
    else if (!currentTerminal || incomingTerminal) {
      if ((message.content?.length ?? 0) >= (current.content?.length ?? 0)) merged[at] = message;
    }
  }
  return merged;
}

/** Persist one conversation's transcript (creates the session dir if needed). */
export async function writeTranscript(
  chatId: string,
  data: Omit<StoredTranscript, "updatedAt">,
): Promise<StoredTranscript> {
  await ensureSessionDirs(chatId);
  const existing = await readTranscript(chatId);
  const incoming = Array.isArray(data.messages) ? data.messages : [];
  const messages = mergeStoredMessages(existing?.messages ?? [], incoming)
    .slice(-MAX_TRANSCRIPT_MESSAGES);
  const stored: StoredTranscript = {
    id: chatId,
    title:
      typeof data.title === "string" && data.title.trim()
        ? data.title
        : existing?.title ?? "",
    messages,
    timestamp: Math.max(
      typeof data.timestamp === "number" ? data.timestamp : 0,
      existing?.timestamp ?? 0,
      Date.now(),
    ),
    createdAt:
      typeof data.createdAt === "number"
        ? Math.min(data.createdAt, existing?.createdAt ?? data.createdAt)
        : existing?.createdAt ?? Date.now(),
    updatedAt: Date.now(),
    forkedFrom: data.forkedFrom ?? existing?.forkedFrom,
    folderId: data.folderId ?? existing?.folderId ?? null,
    color: data.color ?? existing?.color ?? null,
    pinned: data.pinned === true || existing?.pinned === true,
    tags: Array.isArray(data.tags) && data.tags.length > 0 ? data.tags : existing?.tags ?? [],
    archivedAt: data.archivedAt ?? existing?.archivedAt ?? null,
    deletedAt: data.deletedAt ?? existing?.deletedAt ?? null,
  };
  await fs.writeFile(transcriptPath(chatId), JSON.stringify(stored), "utf8");
  invalidateTranscriptList();
  return stored;
}

/** Every persisted conversation, most recently updated first. */
export async function listTranscripts(): Promise<StoredTranscript[]> {
  if (transcriptListCache && Date.now() - transcriptListCache.at < TRANSCRIPT_LIST_TTL_MS) {
    return transcriptListCache.data;
  }
  let entries: import("node:fs").Dirent[];
  try {
    entries = await fs.readdir(sessionsRoot(), { withFileTypes: true });
  } catch {
    return [];
  }
  const out: StoredTranscript[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || !CHAT_ID_RE.test(entry.name)) continue;
    const stored = await readTranscript(entry.name);
    if (stored) out.push(stored);
  }
  out.sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  transcriptListCache = { at: Date.now(), data: out };
  return out;
}

/** Delete one conversation's persisted transcript (files remain). */
export async function deleteTranscript(chatId: string): Promise<void> {
  try {
    await fs.unlink(transcriptPath(chatId));
  } catch {
    // Already absent — nothing to do.
  }
  await clearStoredCompaction(chatId);
  invalidateTranscriptList();
}

// ── Conversation compaction (/compact) ──────────────────────────────────────
//
// A compaction is NOT a transcript rewrite. The browser still shows every
// message, but the older turns are no longer sent to the model: the chat route
// prepends this summary and slices the client history at `through`. Storing it
// beside the transcript makes the effect survive a reload, exactly like the
// transcript itself.
//
// `through` is the conversation length AT compaction time. If the client
// history is shorter (the user cleared or rewrote the chat), the stored
// compaction is ignored rather than applied to the wrong turns.

const COMPACTION_FILE = "compaction.json";

export interface StoredCompaction {
  /** How many turns (before the `/compact` turn) the summary replaces. */
  through: number;
  /** The fenced `<compacted-conversation>` block. */
  block: string;
  droppedTurns: number;
  keptTurns: number;
  at: number;
}

function compactionPath(chatId: string): string {
  return path.join(sessionDir(chatId), COMPACTION_FILE);
}

/** Read the active compaction for a conversation, or null when absent/unusable. */
export async function readStoredCompaction(chatId: string): Promise<StoredCompaction | null> {
  try {
    const raw = await fs.readFile(compactionPath(chatId), "utf8");
    const parsed = JSON.parse(raw) as Partial<StoredCompaction> | null;
    if (!parsed || typeof parsed !== "object") return null;
    if (
      typeof parsed.through !== "number" ||
      !Number.isInteger(parsed.through) ||
      parsed.through < 1 ||
      typeof parsed.block !== "string" ||
      !parsed.block.trim()
    ) {
      return null;
    }
    return {
      through: parsed.through,
      block: parsed.block,
      droppedTurns: typeof parsed.droppedTurns === "number" ? parsed.droppedTurns : 0,
      keptTurns: typeof parsed.keptTurns === "number" ? parsed.keptTurns : 0,
      at: typeof parsed.at === "number" ? parsed.at : Date.now(),
    };
  } catch {
    return null;
  }
}

/** Persist a compaction for a conversation (creates the session dir if needed). */
export async function writeStoredCompaction(
  chatId: string,
  data: Omit<StoredCompaction, "at">,
): Promise<StoredCompaction> {
  await ensureSessionDirs(chatId);
  const stored: StoredCompaction = {
    through: data.through,
    block: data.block,
    droppedTurns: data.droppedTurns,
    keptTurns: data.keptTurns,
    at: Date.now(),
  };
  await fs.writeFile(compactionPath(chatId), JSON.stringify(stored), "utf8");
  return stored;
}

/** Remove a stored compaction (a new/cleared conversation must not keep it). */
export async function clearStoredCompaction(chatId: string): Promise<void> {
  try {
    await fs.unlink(compactionPath(chatId));
  } catch {
    // Already absent — nothing to do.
  }
}

/**
 * Apply a stored compaction to the history a client sent: the summary replaces
 * the first `through` turns and everything after them is kept. Returns the
 * history unchanged when no compaction exists or the client history is shorter
 * than the compaction's boundary.
 */
export function applyStoredCompaction(
  history: Array<{ role: "user" | "assistant"; content: string }>,
  stored: StoredCompaction | null,
): Array<{ role: "user" | "assistant"; content: string }> {
  if (!stored || stored.through < 1) return history;
  if (history.length < stored.through) return history;
  return [{ role: "assistant", content: stored.block }, ...history.slice(stored.through)];
}

export async function loadContextDocuments(chatId: string): Promise<
  Array<{ name: string; text: string; truncated?: boolean; originalChars?: number }>
> {
  if (!CHAT_ID_RE.test(chatId)) return [];
  const files = await listKind(chatId, "context");
  const docs: Array<{ name: string; text: string; truncated?: boolean; originalChars?: number }> = [];
  let total = 0;
  for (const file of files) {
    if (total >= SESSION_LIMITS.maxTotalDocChars) break;
    try {
      const bytes = await readSessionFile(chatId, "context", file.name);
      const result = await extractDocumentText(file.name, bytes);
      if (!result.ok || !result.text) continue;
      const remaining = SESSION_LIMITS.maxTotalDocChars - total;
      const text = result.text.slice(0, remaining);
      total += text.length;
      const truncated = Boolean(result.note) || text.length < result.text.length;
      docs.push({
        name: file.name,
        text,
        ...(truncated
          ? {
              truncated: true,
              originalChars: result.originalChars ?? result.text.length,
            }
          : {}),
      });
    } catch {
      // Unreadable/unsupported file — skip, don't fail the run.
    }
  }
  return docs;
}
