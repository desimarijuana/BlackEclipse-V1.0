// ── Dashboard widget contract ────────────────────────────────────────────────
// Re-exports the shared workspace widget contract. Kept as a thin alias so
// existing dashboard imports keep working while the canonical types live in
// lib/workspace/widget-def.ts (the reusable home).

export {
  WIDGET_CATEGORY_LABEL,
  type WidgetCategory,
  type WidgetConfigField,
  type RefreshPolicy,
  type WidgetDefinition,
} from '@/lib/workspace/widget-def';
export type { WidgetPlacement } from '@/lib/workspace/types';
