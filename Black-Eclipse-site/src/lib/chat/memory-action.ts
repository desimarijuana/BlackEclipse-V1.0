// ── Memory-action presentation model ────────────────────────────────────────
// Pure helpers that turn a run's `memory` blob (explicit-intent outcome +
// learning eligibility) into the render model for the chat surface. Kept out of
// React so the rules are unit-testable without a DOM.
//
// Nothing here invents a field: an absent value stays null/omitted and renders
// as nothing. Presentation only.

export type MemoryActionKind =
  | 'saved'
  | 'forgotten'
  | 'corrected'
  | 'refused'
  | 'needs_confirmation'
  | 'needs_clarification'
  | 'memory_full'
  | 'suggested'
  | 'skill_requested';

export interface MemoryActionView {
  kind: MemoryActionKind;
  /** A single always-visible status line. */
  headline: string;
  /** What was saved/forgotten, when the backend reported it. */
  preview?: string;
  memoryType?: string;
  scope?: string;
  subject?: string;
  /** Link to inspect the affected memory (absent for refused/confirmation). */
  inspectPath?: string;
  /** Link/action to undo (archive) the affected memory. */
  undoPath?: string;
  reason?: string;
  /** For a `suggested` outcome: the inert suggestion awaiting Save/Dismiss. */
  suggestionId?: string;
  suggestionPath?: string;
}

export interface LearningEligibilityView {
  eligible: boolean;
  reason: string;
  /** Always present so the user can reach the Learning Queue. */
  learnQueuePath: string;
  skillRequested: boolean;
  /** True when automatic learning already captured a candidate for this run. */
  autoCaptured: boolean;
  /** How many candidates automatic detection created. */
  candidatesCreated: number;
}

export interface MemoryRunView {
  action?: MemoryActionView;
  eligibility?: LearningEligibilityView;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function str(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function actionView(blob: Record<string, unknown>): MemoryActionView | null {
  const action = str(blob.action);
  const reason = str(blob.reason);
  const preview = str(blob.contentPreview);
  const memoryType = str(blob.memoryType);
  const scope = str(blob.scope);
  const subject = str(blob.subject);
  const inspectPath = str(blob.inspectPath);
  const undoPath = str(blob.undoPath);
  const suggestionId = str(blob.suggestionId);
  const suggestionPath = str(blob.suggestionPath);
  switch (action) {
    case 'saved':
      return { kind: 'saved', headline: 'Remembered', preview, memoryType, scope, subject, inspectPath, undoPath };
    case 'forgotten':
      return { kind: 'forgotten', headline: 'Forgotten', preview, reason };
    case 'corrected':
      return { kind: 'corrected', headline: 'Corrected', preview, subject, inspectPath, undoPath };
    case 'refused':
      return { kind: 'refused', headline: 'Not saved', preview, reason };
    case 'needs_confirmation':
      return { kind: 'needs_confirmation', headline: 'Confirmation needed', preview, reason };
    case 'needs_clarification':
      return { kind: 'needs_clarification', headline: 'Which memory?', preview, reason };
    case 'memory_full':
      return { kind: 'memory_full', headline: 'Memory is full — not saved', preview, reason };
    case 'suggested':
      // NOT saved: a quiet suggestion offered for the user to Save/Dismiss.
      return {
        kind: 'suggested',
        headline: 'Not saved — suggestion',
        preview: str(blob.suggestionContent) ?? preview,
        memoryType: str(blob.suggestionType) ?? memoryType,
        scope: str(blob.suggestionScope) ?? scope,
        reason,
        suggestionId,
        suggestionPath,
      };
    case 'skill_requested':
      return { kind: 'skill_requested', headline: 'Ready to learn from this run', reason };
    default:
      return null;
  }
}

/**
 * Build the view from a run's `memory` blob. Returns null when there is nothing
 * user-visible (no explicit action and no eligibility metadata).
 */
export function buildMemoryRunView(memory: unknown): MemoryRunView | null {
  const blob = asRecord(memory);
  if (!blob) return null;

  const out: MemoryRunView = {};
  const action = actionView(blob);
  if (action) out.action = action;

  const eligibility = asRecord(blob.learningEligibility);
  const analysis = asRecord(blob.learningAnalysis);
  if (eligibility) {
    out.eligibility = {
      eligible: Boolean(eligibility.eligible),
      reason: str(eligibility.reason) ?? '',
      learnQueuePath: str(eligibility.learnQueuePath) ?? '/api/learning/candidates',
      skillRequested: Boolean(eligibility.skillRequested),
      autoCaptured: Boolean(eligibility.autoCaptured),
      candidatesCreated: Number(analysis?.candidatesCreated ?? 0) || 0,
    };
  }

  if (!out.action && !out.eligibility) return null;
  return out;
}
