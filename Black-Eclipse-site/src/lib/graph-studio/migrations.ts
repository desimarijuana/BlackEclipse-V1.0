// ── Workflow IR migrations ────────────────────────────────────────────────────
// The IR schema WILL change. Every persisted document carries `irVersion`; this
// module upgrades an older document to the current version BEFORE it is parsed
// and validated. A document that cannot be migrated is rejected rather than
// silently coerced.
//
// Rules for adding a migration:
//   1. Bump `WORKFLOW_IR_VERSION` in types.ts.
//   2. Add an entry here keyed by the version you are upgrading FROM.
//   3. The migration returns a NEW object with `irVersion` set to the next
//      version. It must be pure and total (never throw on a plausible input).

import { WORKFLOW_IR_VERSION } from './types';
import { defaultSettings, parseWorkflowIR, WorkflowIRError } from './ir';
import type { WorkflowIR } from './types';

type RawDoc = Record<string, unknown>;

/** Migrations keyed by the version they upgrade FROM. */
const MIGRATIONS: Record<number, (doc: RawDoc) => RawDoc> = {
  // 0 → 1: pre-IR / unversioned documents. Ensure the version marker and the
  // settings block exist. (No such documents are stored yet, but the seam is
  // established so the first real schema change is a one-line addition.)
  0: (doc) => ({ ...doc, irVersion: 1, settings: doc.settings ?? defaultSettings() }),
};

export function migrateWorkflowIR(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return raw;
  let doc = raw as RawDoc;
  let version = typeof doc.irVersion === 'number' ? doc.irVersion : 0;
  let guard = 0;
  while (version < WORKFLOW_IR_VERSION) {
    const migrate = MIGRATIONS[version];
    if (!migrate) {
      throw new WorkflowIRError(`No migration path from workflow IR version ${version}`);
    }
    doc = migrate(doc);
    const next = typeof doc.irVersion === 'number' ? doc.irVersion : version + 1;
    if (next <= version) {
      throw new WorkflowIRError(`Migration from version ${version} did not advance the version`);
    }
    version = next;
    guard += 1;
    if (guard > 64) throw new WorkflowIRError('Workflow IR migration did not terminate');
  }
  return doc;
}

/** Migrate (if needed) then validate a stored document. Throws on failure. */
export function readWorkflowIR(raw: unknown): WorkflowIR {
  return parseWorkflowIR(migrateWorkflowIR(raw));
}
