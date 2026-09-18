// ── Shipped default dashboard board ──────────────────────────────────────────
// The arrangement every NEW user gets on first run (and after Reset). Paste the
// exported dashboard layout below (Command Center → Export) so a curated board
// becomes the product default instead of the generic persona template.
//
// How to set it:
//   1. Build the arrangement in the Command Center.
//   2. Click Export and open the downloaded JSON.
//   3. Paste its `layout` object as DEFAULT_BOARD_JSON below.
//
// `DEFAULT_BOARD_JSON` is validated through `normalizeLayout`, so an unknown or
// retired widget id is dropped and a malformed payload falls back to the
// persona templates — a bad paste can never break first run. Set it to `null`
// to ship the persona templates unchanged.

import { normalizeLayout } from '@/lib/workspace/ops';
import type { WorkspaceLayout } from '@/lib/workspace/types';

/** The curated first-run board. `null` = use the persona template. */
export const DEFAULT_BOARD_JSON: unknown = null;

/**
 * Resolved, validated default board (or null to fall back to a persona
 * template). Widget ids are checked against the live registry so a paste that
 * references a removed widget degrades to the template instead of rendering
 * holes.
 */
export function getDefaultBoard(knownWidgetIds: ReadonlySet<string>): WorkspaceLayout | null {
  if (!DEFAULT_BOARD_JSON || typeof DEFAULT_BOARD_JSON !== 'object') return null;
  const normalized = normalizeLayout(DEFAULT_BOARD_JSON, knownWidgetIds);
  if (!normalized) return null;
  const hasWidget = normalized.sections.some(s => s.columns.some(c => c.widgets.length > 0));
  return hasWidget ? normalized : null;
}

/** The dashboard title new users see when the curated board is seeded. */
export const DEFAULT_BOARD_NAME = 'Command Center';
