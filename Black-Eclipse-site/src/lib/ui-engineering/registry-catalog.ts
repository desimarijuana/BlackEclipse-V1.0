// ── Catalog from the live widget registry ────────────────────────────────────
// Bridges the existing dashboard widget registry into the catalog. Kept in its
// own module (not index.ts) so the pure UI-engineering core never pulls React
// or the component library into framework-free consumers/tests.
'use client';

import { DASHBOARD_WIDGETS } from '@/lib/dashboard/registry';
import { adaptWidgetDefinition, ComponentCatalog, type UiComponentSpec } from './catalog';

export function dashboardComponentSpecs(): UiComponentSpec[] {
  return DASHBOARD_WIDGETS.map(def => adaptWidgetDefinition(def));
}

export function buildDashboardCatalog(): ComponentCatalog {
  return new ComponentCatalog(dashboardComponentSpecs());
}
