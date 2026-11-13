// Server-side self-heal for conversations whose last turn never got its answer.
//
// The browser writes a transcript in two steps: an EMPTY `status: "queued"`
// assistant placeholder at send time, then the real answer when the run
// resolves in that same tab. If the tab reloads, the app restarts, or the run is
// recovered elsewhere, the placeholder stays empty forever — the answer exists
// in the run store (`HarnessRun.output`) but never reaches the conversation.
//
// This module closes that gap WITHOUT touching the streaming path: when the
// transcript list is read, any stuck last turn is matched to its completed run
// and filled from the stored output. It is read-only against the runtime,
// conservative (completed runs only), throttled, and a no-op when nothing is
// stuck.

import { getRunFromRuntime, listRunsFromRuntime } from "@/lib/harness";
import type { RunRecord } from "@/lib/harness/types";
import type { Message } from "@/types/chat";
import { writeTranscript, type StoredTranscript } from "./session-store";

/** Non-terminal lifecycle states a placeholder can be stuck in. */
const PENDING_STATUSES = new Set([
  "queued",
  "planning",
  "tool_running",
  "streaming",
  "awaiting_approval",
]);

/** One repair pass per five minutes at most; boot reads are frequent. */
const RECONCILE_INTERVAL_MS = 5 * 60_000;
/** A run must start within this window AFTER the prompt to belong to it. */
const RUN_AFTER_PROMPT_SLACK_MS = 60_000;

let lastAttemptMs = 0;

/** Reset the throttle (tests only). */
export function resetReconcileThrottle(): void {
  lastAttemptMs = 0;
}

function textOf(message: Message | undefined): string {
  return typeof message?.content === "string" ? message.content : "";
}

/**
 * The index of the turn that needs an answer, or null.
 *
 * `messages.length` means "append a missing assistant turn" (the user prompt is
 * the last message). A non-empty or honestly-failed turn is never touched.
 */
export function indexOfStuckTurn(messages: Message[]): number | null {
  if (messages.length === 0) return null;
  const last = messages[messages.length - 1];
  if (last.role === "assistant") {
    if (textOf(last).trim()) return null;
    const status = last.status as string | undefined;
    return status === undefined || PENDING_STATUSES.has(status) ? messages.length - 1 : null;
  }
  if (last.role === "user") return messages.length;
  return null;
}

/** Epoch ms of the last user turn, from its client-side id (`Date.now()`). */
export function lastUserEpochMs(messages: Message[]): number {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role !== "user") continue;
    const parsed = Number(message.id);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

/** True when a completed run plausibly answers the turn that follows it. */
export function runAnswersTurn(run: RunRecord, promptEpochMs: number): boolean {
  if (run.status !== "completed") return false;
  if (!String(run.output ?? "").trim()) return false;
  const createdAt = Date.parse(run.createdAt);
  if (!Number.isFinite(createdAt)) return true;
  return createdAt + RUN_AFTER_PROMPT_SLACK_MS >= promptEpochMs;
}

/** Apply a completed run's answer to the stuck turn (replace or append). */
export function withRunApplied(messages: Message[], turnIndex: number, run: RunRecord): Message[] {
  const answer = String(run.output ?? "").trim();
  const started = Date.parse(run.startedAt ?? "");
  const finished = Date.parse(run.finishedAt ?? "");
  const durationMs =
    Number.isFinite(started) && Number.isFinite(finished) ? Math.max(0, finished - started) : undefined;
  const base: Message = {
    id: String(Date.parse(run.createdAt) + 1 || Date.now()),
    role: "assistant",
    content: answer,
    status: "completed",
    runId: run.id,
    ...(durationMs !== undefined ? { durationMs } : {}),
  };
  if (turnIndex < 0 || turnIndex >= messages.length) return [...messages, base];
  const existing = messages[turnIndex];
  const filled: Message = {
    ...existing,
    content: answer,
    status: "completed",
    runId: run.id,
    ...(durationMs !== undefined ? { durationMs } : {}),
  };
  delete filled.error;
  const next = [...messages];
  next[turnIndex] = filled;
  return next;
}

/**
 * Fill every stuck conversation from the run store. Returns the (possibly
 * updated) list. Never throws: a dead runtime or an unwritable file leaves the
 * conversation exactly as it was.
 */
export async function reconcileStuckTranscripts(
  transcripts: StoredTranscript[],
): Promise<StoredTranscript[]> {
  const stuck = transcripts.filter((entry) => indexOfStuckTurn(entry.messages) !== null);
  if (stuck.length === 0) return transcripts;
  const now = Date.now();
  if (now - lastAttemptMs < RECONCILE_INTERVAL_MS) return transcripts;
  lastAttemptMs = now;

  let runs: RunRecord[];
  try {
    runs = await listRunsFromRuntime(50);
  } catch {
    return transcripts; // runtime down / too slow: try again on a later read
  }

  const byId = new Map<string, RunRecord>();
  const bySession = new Map<string, RunRecord>();
  for (const run of runs) {
    byId.set(run.id, run);
    const sessionId = run.sessionId ?? "";
    // Newest-first: only a completed run with real output may claim a session.
    if (sessionId && !bySession.has(sessionId) && run.status === "completed" && String(run.output ?? "").trim()) {
      bySession.set(sessionId, run);
    }
  }

  const updated: StoredTranscript[] = [];
  for (const entry of transcripts) {
    const turnIndex = indexOfStuckTurn(entry.messages);
    if (turnIndex === null) {
      updated.push(entry);
      continue;
    }
    const stuckTurn = entry.messages[turnIndex];
    let run = stuckTurn?.runId ? byId.get(stuckTurn.runId) : undefined;
    if (!run && stuckTurn?.runId) {
      try {
        run = (await getRunFromRuntime(stuckTurn.runId)) ?? undefined;
      } catch {
        run = undefined;
      }
    }
    if (!run) run = bySession.get(entry.id);
    if (!run || !runAnswersTurn(run, lastUserEpochMs(entry.messages))) {
      updated.push(entry);
      continue;
    }
    const messages = withRunApplied(entry.messages, turnIndex, run);
    try {
      await writeTranscript(entry.id, { ...entry, messages });
    } catch {
      updated.push(entry);
      continue;
    }
    updated.push({ ...entry, messages });
  }
  return updated;
}
