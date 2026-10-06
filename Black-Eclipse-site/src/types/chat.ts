import type { ActivityItem, PendingApproval, ResponseStatus, TurnError } from '@/lib/agent/response-model';

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
  /**
   * Phase 14: the run's code-verification ledger when the turn used the code
   * capability. Absent on user turns, ordinary chat, and legacy rows. Narrowed
   * by the chat capability panel via `coerceCodeVerification`.
   */
  codeVerification?: unknown;
  /**
   * Phase 14: the narrow code profile the turn was bound to
   * (`plan_only` | `edit_verify`), or null/absent for an ordinary turn.
   */
  autonomy?: string | null;
  /** Phase 14 §6.4: the runtime-derived chat capability view, when any. */
  capability?: unknown;
  /**
   * The action the agent is blocked on pending an operator decision. Present
   * only while a run is paused on an approval card; set from the
   * `approval.requested` event and cleared when it resolves.
   */
  pendingApproval?: PendingApproval;
  /** A recoverable failure on this turn. */
  error?: TurnError;
  /** User rating on an assistant turn, if given. Persisted with the message. */
  feedback?: 'up' | 'down';
}
