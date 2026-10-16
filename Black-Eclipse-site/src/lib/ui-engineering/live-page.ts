// ── Live page bridge: blueprint layout ⇄ workspace kernel layout ─────────────
// A blueprint's layout is ALREADY the workspace kernel's `WorkspaceLayout` tree
// (the UI-Engineering foundation wraps it), but the wire form returned by the
// Python runtime is a looser shape (nullable fields, `zone: string`). These
// pure functions are the ONE place that translates between the two, so the
// live Pages surface can render a blueprint through the SAME
// `CustomizableWorkspace` the dashboards use — and write a user's arrangement
// back as a durable blueprint revision. No layout logic lives here: it only
// normalizes types.

import type {
  WorkspaceColumn as KernelColumn,
  WorkspaceLayout as KernelLayout,
  WorkspaceSection as KernelSection,
  WorkspaceZone,
  WidgetPlacement as KernelPlacement,
} from '@/lib/workspace/types';
import type {
  WorkspaceLayout as WireLayout,
  WidgetPlacement as WirePlacement,
} from '@/lib/harness/ui-client';

/** localStorage key under which a live page's user arrangement is cached. */
export const LIVE_PAGE_STORAGE_PREFIX = 'be_ui_page_';

/**
 * The per-page cache key. Derived from the blueprint id AND (when given) its
 * revision, so a new durable revision — an agent edit, or the user's own
 * "Save to page" — seeds a fresh workspace instead of being shadowed by a
 * stale local arrangement. Omitting the revision keeps the legacy key.
 */
export function pageStorageKey(blueprintId: string, revision?: number): string {
  return `${LIVE_PAGE_STORAGE_PREFIX}${blueprintId}${revision != null ? `_r${revision}` : ''}`;
}

function asZone(value: unknown): WorkspaceZone | undefined {
  return value === 'left' || value === 'right' || value === 'main' ? value : undefined;
}

/** Wire blueprint layout → kernel layout. Nullable/loose fields become defaults. */
export function blueprintLayoutToKernel(raw: WireLayout | null | undefined): KernelLayout {
  const sections: KernelSection[] = (raw?.sections ?? []).map((section) => ({
    id: section.id,
    zone: asZone(section.zone),
    columns: (section.columns ?? []).map((column): KernelColumn => ({
      id: column.id,
      weight: typeof column.weight === 'number' && column.weight > 0 ? column.weight : 3,
      widgets: (column.widgets ?? []).map((widget): KernelPlacement => {
        const placement: KernelPlacement = {
          id: widget.id,
          widgetId: widget.widgetId,
          height: typeof widget.height === 'number' ? widget.height : null,
        };
        if (typeof widget.defaultHeight === 'number') placement.defaultHeight = widget.defaultHeight;
        if (typeof widget.minHeight === 'number') placement.minHeight = widget.minHeight;
        if (widget.config && typeof widget.config === 'object') placement.config = { ...widget.config };
        if (widget.hidden) placement.hidden = true;
        return placement;
      }),
    })),
  }));

  const layout: KernelLayout = { version: 2, sections };
  const hidden = (raw?.hiddenZones ?? []).map(asZone).filter((z): z is WorkspaceZone => z !== undefined);
  if (hidden.length) layout.hiddenZones = hidden;
  if (raw?.zoneWidths) layout.zoneWidths = { ...raw.zoneWidths };
  return layout;
}

/** Kernel layout → wire blueprint layout. The reverse mapping for `save_layout`. */
export function kernelLayoutToWire(layout: KernelLayout): WireLayout {
  return {
    version: layout.version,
    sections: layout.sections.map((section) => ({
      id: section.id,
      zone: section.zone ?? 'main',
      columns: section.columns.map((column) => ({
        id: column.id,
        weight: column.weight,
        widgets: column.widgets.map((widget): WirePlacement => ({
          id: widget.id,
          widgetId: widget.widgetId,
          height: widget.height,
          defaultHeight: widget.defaultHeight ?? null,
          minHeight: widget.minHeight ?? null,
          config: widget.config ?? null,
          hidden: widget.hidden ?? null,
        })),
      })),
    })),
    hiddenZones: layout.hiddenZones ?? null,
    zoneWidths: layout.zoneWidths ?? null,
  };
}
