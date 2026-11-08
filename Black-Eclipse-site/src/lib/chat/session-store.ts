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
import { extractText, extractDocumentText, isTextExtractable } from "./extract";
import { SESSION_LIMITS, type SessionFile, type SessionFileKind, type SessionInfo } from "./session-types";

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
      });
    } catch {
      // Vanished between readdir and stat — skip.
    }
  }
  return files.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
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
}

/** Write a file into a session (upload or agent output). Returns its metadata. */
export async function writeSessionFile(
  chatId: string,
  { name, bytes, kind }: WriteFileOptions
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
  const stat = await fs.stat(full);
  return {
    name: safeName,
    kind,
    bytes: stat.size,
    updatedAt: stat.mtime.toISOString(),
    textExtractable: isTextExtractable(safeName),
  };
}

export async function readSessionFile(chatId: string, kind: SessionFileKind, name: string): Promise<Buffer> {
  return fs.readFile(resolveFile(chatId, kind, name));
}

export async function deleteSessionFile(chatId: string, kind: SessionFileKind, name: string): Promise<void> {
  await fs.unlink(resolveFile(chatId, kind, name));
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

/** Persist one conversation's transcript (creates the session dir if needed). */
export async function writeTranscript(
  chatId: string,
  data: Omit<StoredTranscript, "updatedAt">,
): Promise<StoredTranscript> {
  await ensureSessionDirs(chatId);
  const messages = Array.isArray(data.messages)
    ? data.messages.slice(-MAX_TRANSCRIPT_MESSAGES)
    : [];
  const stored: StoredTranscript = {
    id: chatId,
    title: typeof data.title === "string" ? data.title : "",
    messages,
    timestamp: typeof data.timestamp === "number" ? data.timestamp : Date.now(),
    createdAt: typeof data.createdAt === "number" ? data.createdAt : Date.now(),
    updatedAt: Date.now(),
    folderId: data.folderId ?? null,
    color: data.color ?? null,
    pinned: data.pinned === true,
    tags: Array.isArray(data.tags) ? data.tags : [],
    archivedAt: data.archivedAt ?? null,
    deletedAt: data.deletedAt ?? null,
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
  invalidateTranscriptList();
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
