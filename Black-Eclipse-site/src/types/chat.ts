import type { ActivityItem, AssistantModel, PendingApproval, PendingClarification, ResponsePlan, ResponseStatus, TurnChange, TurnError } from '@/lib/agent/response-model';

/**
 * A context document a user turn carried into the run. Persisted ON the message
 * so the transcript can show WHAT was sent, not just the typed prompt — a
 * pasted wall of text must not vanish into an invisible attachment.
 */
export interface MessageAttachment {
  /** Session file name, e.g. `pasted-text.txt`. */
  name: string;
  /** Extracted characters, when known (pasted text always reports this). */
  chars?: number;
  /** A short excerpt so the content is recognizable in the transcript. */
  preview?: string;
  /** True when the user pasted the text into the composer. */
  pasted?: boolean;
}

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
  /**
   * Context documents the user attached to THIS turn. Present on user turns
   * only; absent on assistant turns, ordinary prompts and legacy rows.
   */
  attachments?: MessageAttachment[];
  /** Lifecycle of an assistant turn (absent on user turns and legacy rows). */
  status?: ResponseStatus;
  /** Tools/retrieval the agent used while producing this turn. */
  activities?: ActivityItem[];
  /**
   * Code changes the turn made, with the runtime's bounded diff previews.
   * Absent on user turns, change-free runs, and legacy rows.
   */
  changes?: TurnChange[];
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
   * The provider + model that actually served this turn (from the run record).
   * Absent on user turns, legacy rows, and runs that reported no model.
   */
  model?: AssistantModel;
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
   * Generated-capability lifecycle (request, build, test, activation) for this
   * turn. Absent on user turns and legacy rows; narrowed by the chat surface via
   * `coerceCapabilityBuild`.
   */
  capabilityBuild?: unknown;
  /**
   * Vision/Multimodal: the run's collected vision results (asset ids, regions,
   * OCR, confidence, provenance). Absent on user turns, non-vision runs, and
   * legacy rows. Narrowed by the chat surface via `coerceVisionRun`.
   */
  vision?: unknown;
  /**
   * Document Intelligence: the run's collected document results. Absent on user
   * turns, non-document runs, and legacy rows. Narrowed by the chat surface via
   * `coerceDocumentRun`.
   */
  documents?: unknown;
  /**
   * Internet Image Search: the run's validated, normalized image results for the
   * chat's inline gallery. Absent on user turns, non-image runs, and legacy rows.
   * Narrowed by the chat surface via `coerceGalleryBlob`.
   */
  images?: unknown;
  /**
   * Native video: the video jobs this run queued (job + project ids) for the
   * chat's live job card — polling, playback, download, revise/regenerate.
   * Absent on user turns, non-video runs, and legacy rows. Narrowed by the chat
   * surface via `coerceVideoBlob`.
   */
  video?: unknown;
  /**
   * A computed result the runtime worked out on this turn (`analysis.completed`):
   * outputs, artifacts and provenance. Absent on user turns, computation-free
   * runs and legacy rows. Narrowed by the chat surface via `coerceComputedResult`.
   */
  analysis?: unknown;
  /**
   * A dataset collection this turn completed (`acquire.completed`): the pull
   * manifest (source, window, rows, completeness, licence, attribution). Absent
   * on user turns, collection-free runs and legacy rows. Narrowed by the chat
   * surface via `coerceAcquisitionManifest`.
   */
  acquisition?: unknown;
  /**
   * The action the agent is blocked on pending an operator decision. Present
   * only while a run is paused on an approval card; set from the
   * `approval.requested` event and cleared when it resolves.
   */
  pendingApproval?: PendingApproval;
  /**
   * A question the agent is paused on (`clarify`). Present only while the run
   * waits for the operator's answer; cleared when it resolves.
   */
  pendingClarification?: PendingClarification;
  /**
   * The Intelligent Response Orchestrator's presentation plan for this turn
   * (runtime `response.plan`). Absent for ordinary/legacy turns. Display only.
   */
  responsePlan?: ResponsePlan;
  /** A recoverable failure on this turn. */
  error?: TurnError;
  /** User rating on an assistant turn, if given. Persisted with the message. */
  feedback?: 'up' | 'down';
  /**
   * Wall-clock time the turn took, from send to settled (ms). Computed
   * client-side by the run owners; absent on user turns and legacy rows.
   */
  durationMs?: number;
  /**
   * Who produced this assistant turn when it is NOT the main Eclipse agent: a
   * bot or group-chat member the user `@`-mentioned in the main composer. Absent
   * on ordinary Eclipse replies, user turns, and legacy rows.
   */
  author?: { id: string; kind: 'bot' | 'group'; name: string };
}
