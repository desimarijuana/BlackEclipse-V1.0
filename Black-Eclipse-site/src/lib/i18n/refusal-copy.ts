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
};

export function refusalKey(code: string | null | undefined): TranslationKey {
  if (code && code in REFUSAL_KEY) return REFUSAL_KEY[code];
  return REFUSAL_FALLBACK_KEY;
}
