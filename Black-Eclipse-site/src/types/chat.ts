import type { ActivityItem, ResponseStatus, TurnError } from '@/lib/agent/response-model';

/**
 * One turn in a conversation transcript.
 *
 * `status`, `activities` and `error` are OPTIONAL so conversations persisted
 * before they existed (plain `{ id, role, content }` rows in localStorage) still
 * load unchanged. A missing status means "a finished turn with no metadata",
 * which is exactly how older assistant messages should read.
 */
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** Lifecycle of an assistant turn (absent on user turns and legacy rows). */
  status?: ResponseStatus;
  /** Tools/retrieval the agent used while producing this turn. */
  activities?: ActivityItem[];
  /**
   * Phase 4 evidence-grounded research metadata for a gated run (coverage,
   * citations, claims, gaps). Absent on user turns, ordinary chat, and legacy
   * rows. Narrowed by the chat surface via `ResearchRunInfo`.
   */
  research?: unknown;
  /**
   * Phase 3-M Reliability: explicit memory-intent outcome (saved/forgotten/
   * corrected/refused/needs_confirmation) and learning eligibility for an
   * ordinary chat run. Absent on user turns, skill runs and legacy rows.
   */
  memory?: unknown;
  /** The harness run id for this turn (enables run-scoped actions/diagnostics). */
  runId?: string;
  /** A recoverable failure on this turn. */
  error?: TurnError;
  /** User rating on an assistant turn, if given. Persisted with the message. */
  feedback?: 'up' | 'down';
}
