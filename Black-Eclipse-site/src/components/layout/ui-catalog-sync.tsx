'use client';

// ── Runtime catalog sync (mounted once in the app shell) ──────────────────────
// Seeds the Python UI runtime's component catalog with the REAL dashboard
// widget specs on first app load, so the agent can Compose with them without
// the user having to open the UI Builder first. Fire-and-forget and idempotent;
// the runtime persists the specs on agent-memory.db, so it is effectively a
// one-time install step.

import { useEffect } from 'react';

export function UiCatalogSync() {
  useEffect(() => {
    // Lazy-load the sync so its dependency chain (the dashboard widget
    // registry → full ECharts) stays OUT of the initial route bundle. A static
    // import here pulled the entire ECharts library into the root `/` graph,
    // defeating the code-splitting in stock-chat.tsx and inflating dev compile
    // time and server memory. It is fire-and-forget, so loading it after mount
    // is equivalent.
    void import('@/lib/harness/ui-sync').then((m) => {
      void m.syncCoreCatalog();
      void m.syncAppSurfaces();
    });
    // User-created SDK widgets are runtime data, not part of the static
    // registry. Hydrate them on boot so the Pages widget library can place them
    // even if the SDK screen was never opened.
    void import('@/lib/sdk/widgets').then((m) => m.hydrateSdkWidgets());
  }, []);
  return null;
}
