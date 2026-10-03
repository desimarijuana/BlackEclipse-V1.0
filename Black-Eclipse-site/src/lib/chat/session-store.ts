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
import { extractText, isTextExtractable } from "./extract";
import { SESSION_LIMITS, type SessionFile, type SessionFileKind, type SessionInfo } from "./session-types";

const CHAT_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

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

function sessionDir(chatId: string): string {
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
      const result = extractText(file.name, bytes);
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
 * set of documents cannot blow the context window.
 */
export async function loadContextDocuments(chatId: string): Promise<Array<{ name: string; text: string }>> {
  if (!CHAT_ID_RE.test(chatId)) return [];
  const files = await listKind(chatId, "context");
  const docs: Array<{ name: string; text: string }> = [];
  let total = 0;
  for (const file of files) {
    if (total >= SESSION_LIMITS.maxTotalDocChars) break;
    try {
      const bytes = await readSessionFile(chatId, "context", file.name);
      const result = extractText(file.name, bytes);
      if (!result.ok || !result.text) continue;
      const remaining = SESSION_LIMITS.maxTotalDocChars - total;
      const text = result.text.slice(0, remaining);
      total += text.length;
      docs.push({ name: file.name, text });
    } catch {
      // Unreadable/unsupported file — skip, don't fail the run.
    }
  }
  return docs;
}
