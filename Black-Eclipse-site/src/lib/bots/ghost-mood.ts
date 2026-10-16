// ── Ghost mood model ─────────────────────────────────────────────────────────
// What the bot's face is *feeling*, derived from the agent turn it is running.
// This is the one vocabulary that turns the runtime's lifecycle (a
// `ResponseStatus` or a normalized `HarnessUiEvent`) into a face expression the
// `LiveGhostAvatar` renders as a CSS animation.
//
// Pure data + mapping — no React, no DOM. The visual meaning of each mood lives
// in `globals.css` (`.be-ghost[data-mood="…"]`), so this module stays a pure,
// testable contract.

import type { ResponseStatus } from '@/lib/agent/response-model';
import type { HarnessUiEvent } from '@/lib/agent/events';

/**
 * The face expressions a live bot can wear.
 * - `idle`     — resting: breathe + blink.
 * - `thinking` — planning: eyes look up, a slow ponder.
 * - `working`  — running tools: eyes dart side to side.
 * - `speaking` — writing the answer: the mouth moves.
 * - `waiting`  — blocked on an approval: eyes up, patient.
 * - `happy`    — a turn completed: a little hop and squint.
 * - `sad`      — a turn failed or was cancelled: a droop.
 */
export type GhostMood =
  | 'idle'
  | 'thinking'
  | 'working'
  | 'speaking'
  | 'waiting'
  | 'happy'
  | 'sad';

/** Map the coarse turn lifecycle to a face. */
export function moodFromStatus(status: ResponseStatus): GhostMood {
  switch (status) {
    case 'queued':
    case 'planning':
      return 'thinking';
    case 'tool_running':
      return 'working';
    case 'streaming':
      return 'speaking';
    case 'awaiting_approval':
      return 'waiting';
    case 'completed':
      return 'happy';
    case 'error':
    case 'cancelled':
      return 'sad';
    default:
      return 'idle';
  }
}

/**
 * Map one normalized UI event to a face, or `null` when the event should not
 * change the current mood (deltas mid-answer, change notifications, …).
 */
export function moodFromEvent(event: HarnessUiEvent): GhostMood | null {
  switch (event.kind) {
    case 'status':
      return moodFromStatus(event.status);
    case 'activity_start':
      return 'working';
    case 'delta':
      return 'speaking';
    case 'approval_request':
      return 'waiting';
    case 'final':
      return event.error ? 'sad' : 'happy';
    case 'error':
      return 'sad';
    default:
      return null;
  }
}
