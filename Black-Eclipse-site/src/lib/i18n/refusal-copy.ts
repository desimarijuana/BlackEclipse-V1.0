// ── Refusal copy map (data, not branching UI) ────────────────────────────────
// Maps a machine refusal code to the i18n KEY that holds its one plain sentence.
// UI renders the sentence via `t(REFUSAL_KEY[code])`; the code itself belongs
// behind the "details" affordance, never as the primary message. Keeping this a
// dictionary (not a chain of ifs) is what makes it testable and translatable.
//
// A code with no entry falls back to `refusal.fallback`: honest, never a raw
// mechanism term.

import type { TranslationKey } from './types';

export const REFUSAL_FALLBACK_KEY: TranslationKey = 'refusal.NOT_FOUND';

export const REFUSAL_KEY: Record<string, TranslationKey> = {
  PROTECTED_PATH: 'refusal.PROTECTED_PATH',
  PATH_TRAVERSAL: 'refusal.PATH_TRAVERSAL',
  PATH_OUTSIDE_WORKSPACE: 'refusal.PATH_OUTSIDE_WORKSPACE',
  SYMLINK_ESCAPE: 'refusal.SYMLINK_ESCAPE',
  IGNORED_PATH: 'refusal.IGNORED_PATH',
  NOT_FOUND: 'refusal.NOT_FOUND',
  BINARY_FILE: 'refusal.BINARY_FILE',
  TOO_LARGE: 'refusal.TOO_LARGE',
  WORKSPACE_UNAVAILABLE: 'refusal.WORKSPACE_UNAVAILABLE',
  INVALID_PATTERN: 'refusal.INVALID_PATTERN',
  // Phase 2 authoring refusals.
  PATCH_PATH_ABSOLUTE: 'refusal.PATCH_PATH_ABSOLUTE',
  PATCH_PATH_TRAVERSAL: 'refusal.PATCH_PATH_TRAVERSAL',
  PATCH_PATH_SYMLINK: 'refusal.PATCH_PATH_SYMLINK',
  PATCH_PROTECTED_PATH: 'refusal.PATCH_PROTECTED_PATH',
  PATCH_OUTSIDE_SCOPE: 'refusal.PATCH_OUTSIDE_SCOPE',
  PATCH_BASE_MISMATCH: 'refusal.PATCH_BASE_MISMATCH',
  PATCH_TOO_LARGE: 'refusal.PATCH_TOO_LARGE',
  PATCH_SPAN_NOT_FOUND: 'refusal.PATCH_SPAN_NOT_FOUND',
  PATCH_SPAN_AMBIGUOUS: 'refusal.PATCH_SPAN_AMBIGUOUS',
  PATCH_FILE_EXISTS: 'refusal.PATCH_FILE_EXISTS',
  PATCH_FILE_MISSING: 'refusal.PATCH_FILE_MISSING',
  PATCH_MALFORMED: 'refusal.PATCH_MALFORMED',
  PATCH_UNKNOWN_OP: 'refusal.PATCH_UNKNOWN_OP',
  PATCH_TOO_MANY_OPERATIONS: 'refusal.PATCH_TOO_MANY_OPERATIONS',
  PROFILE_DENIED: 'refusal.PROFILE_DENIED',
  WORKSPACE_UNBOUND: 'refusal.WORKSPACE_UNBOUND',
  UNKNOWN_WORKSPACE: 'refusal.UNKNOWN_WORKSPACE',
  // Phase 3 command refusals.
  COMMAND_NOT_ALLOWLISTED: 'refusal.COMMAND_NOT_ALLOWLISTED',
  COMMAND_NOT_ENABLED: 'refusal.COMMAND_NOT_ENABLED',
  COMMAND_EXECUTABLE_MISSING: 'refusal.COMMAND_EXECUTABLE_MISSING',
  COMMAND_ARG_INVALID: 'refusal.COMMAND_ARG_INVALID',
  SANDBOX_UNAVAILABLE: 'refusal.SANDBOX_UNAVAILABLE',
  COMMAND_REFUSED: 'refusal.COMMAND_REFUSED',
  // Phase 11 delivery refusals.
  NO_DESTINATION: 'refusal.NO_DESTINATION',
  DELIVERY_FAILED: 'refusal.DELIVERY_FAILED',
  REFUSED: 'refusal.REFUSED',
};

export function refusalKey(code: string | null | undefined): TranslationKey {
  if (code && code in REFUSAL_KEY) return REFUSAL_KEY[code];
  return REFUSAL_FALLBACK_KEY;
}
