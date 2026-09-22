// SERVER-ONLY: per-conversation checkpoints on disk.
//
// A checkpoint is a small JSON snapshot of a conversation's turns at a moment
// the user chose. Restoring replaces the conversation state with the snapshot —
// like an editor save point, so a bad turn can be rolled back.
//
// Layout (inside the session folder, gitignored):
//
//   <repo>/.black-eclipse/sessions/<chatId>/checkpoints/<id>.json
//
// The chat id is untrusted input used as a path segment, so it is validated
// exactly as `session-store.ts` does.

import { promises as fs } from "node:fs";
import path from "node:path";
import { sessionsRoot, SessionError } from "./session-store";
import type { Checkpoint, CheckpointSnapshot } from "./session-types";

const CHAT_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const CHECKPOINT_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const MAX_CHECKPOINTS_PER_CHAT = 50;
/** Hard cap on a snapshot so a checkpoint cannot grow unbounded. */
const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024;
const MAX_LABEL_LEN = 120;

function assertChatId(chatId: string): string {
  if (!CHAT_ID_RE.test(chatId)) throw new SessionError("INVALID_CHAT_ID", "Invalid conversation id");
  return chatId;
}

function assertCheckpointId(id: string): string {
  if (!CHECKPOINT_ID_RE.test(id)) throw new SessionError("INVALID_CHECKPOINT_ID", "Invalid checkpoint id");
  return id;
}

function checkpointsDir(chatId: string): string {
  const root = sessionsRoot();
  const dir = path.resolve(root, assertChatId(chatId), "checkpoints");
  if (dir !== root && !dir.startsWith(root + path.sep)) {
    throw new SessionError("INVALID_CHAT_ID", "Invalid conversation id");
  }
  return dir;
}

function checkpointPath(chatId: string, id: string): string {
  const dir = checkpointsDir(chatId);
  const full = path.resolve(dir, `${assertCheckpointId(id)}.json`);
  if (!full.startsWith(dir + path.sep)) {
    throw new SessionError("INVALID_CHECKPOINT_ID", "Invalid checkpoint id");
  }
  return full;
}

function sanitizeLabel(label: string): string {
  const trimmed = label.replace(/[\r\n]+/g, " ").trim();
  return (trimmed || "Checkpoint").slice(0, MAX_LABEL_LEN);
}

function newCheckpointId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Create a checkpoint from a conversation snapshot. Returns its metadata. */
export async function createCheckpoint(
  chatId: string,
  label: string,
  messages: Array<{ id: string; role: string; content: string }>
): Promise<Checkpoint> {
  const dir = checkpointsDir(chatId);
  await fs.mkdir(dir, { recursive: true });

  const id = newCheckpointId();
  const snapshot: CheckpointSnapshot = {
    chatId,
    label: sanitizeLabel(label),
    createdAt: new Date().toISOString(),
    messages,
  };
  const payload = JSON.stringify(snapshot);
  if (Buffer.byteLength(payload, "utf8") > MAX_SNAPSHOT_BYTES) {
    throw new SessionError("CHECKPOINT_TOO_LARGE", "Conversation is too large to checkpoint");
  }
  await fs.writeFile(checkpointPath(chatId, id), payload, "utf8");

  // Prune the oldest when over the cap (best-effort).
  const existing = await listCheckpoints(chatId);
  if (existing.length > MAX_CHECKPOINTS_PER_CHAT) {
    for (const stale of existing.slice(MAX_CHECKPOINTS_PER_CHAT)) {
      await fs.unlink(checkpointPath(chatId, stale.id)).catch(() => undefined);
    }
  }

  return {
    id,
    chatId,
    label: snapshot.label,
    createdAt: snapshot.createdAt,
    messageCount: messages.length,
    bytes: Buffer.byteLength(payload, "utf8"),
  };
}

/** List a conversation's checkpoints, newest first. */
export async function listCheckpoints(chatId: string): Promise<Checkpoint[]> {
  const dir = checkpointsDir(chatId);
  let entries: import("node:fs").Dirent[];
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const out: Checkpoint[] = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
    const id = entry.name.slice(0, -5);
    if (!CHECKPOINT_ID_RE.test(id)) continue;
    try {
      const raw = await fs.readFile(path.join(dir, entry.name), "utf8");
      const parsed = JSON.parse(raw) as CheckpointSnapshot;
      out.push({
        id,
        chatId,
        label: typeof parsed.label === "string" ? parsed.label : "Checkpoint",
        createdAt: typeof parsed.createdAt === "string" ? parsed.createdAt : "",
        messageCount: Array.isArray(parsed.messages) ? parsed.messages.length : 0,
        bytes: Buffer.byteLength(raw, "utf8"),
      });
    } catch {
      // A corrupt snapshot is skipped rather than breaking the list.
    }
  }
  return out.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

/** Read one checkpoint's snapshot for restore. */
export async function readCheckpoint(chatId: string, id: string): Promise<CheckpointSnapshot | null> {
  try {
    const raw = await fs.readFile(checkpointPath(chatId, id), "utf8");
    const parsed = JSON.parse(raw) as CheckpointSnapshot;
    if (!Array.isArray(parsed.messages)) return null;
    return parsed;
  } catch {
    return null;
  }
}

/** Delete one checkpoint. */
export async function deleteCheckpoint(chatId: string, id: string): Promise<void> {
  await fs.unlink(checkpointPath(chatId, id)).catch((err: NodeJS.ErrnoException) => {
    if (err.code !== "ENOENT") throw err;
  });
}
