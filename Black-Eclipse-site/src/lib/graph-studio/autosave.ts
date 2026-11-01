// ── Auto-save policy ─────────────────────────────────────────────────────────
// The editor persists a graph a short pause after the last edit. The decision is
// a pure function so it is testable without mounting the screen (and so the
// manual Save button and auto-save can never disagree about what is savable).

/** How long the editor stays quiet before it saves. */
export const AUTO_SAVE_DELAY_MS = 2_000;

export interface AutoSaveInputs {
  /** The operator's Auto-save toggle. */
  enabled: boolean;
  /** The document differs from the last saved version. */
  dirty: boolean;
  /** A save (manual or automatic) is already in flight. */
  busy: boolean;
  /** Validation errors currently on the graph. */
  errors: number;
  /** A persisted workflow id exists (a brand-new graph is created on save). */
  hasWorkflow: boolean;
  /** The editor holds a document. */
  hasIr: boolean;
  /** The document's content differs from the last saved version. */
  changed: boolean;
}

/**
 * Auto-save only when it would succeed: there is something to save, the graph
 * is valid, no save is running, and the operator left the toggle on. An invalid
 * graph is never written — the same rule the Save button enforces. A document
 * whose content hash matches the saved version is skipped, so opening the
 * editor (which can dispatch a no-op layout patch) never creates a version.
 */
export function shouldAutoSave(state: AutoSaveInputs): boolean {
  return (
    state.enabled
    && state.dirty
    && state.changed
    && !state.busy
    && state.errors === 0
    && state.hasWorkflow
    && state.hasIr
  );
}
