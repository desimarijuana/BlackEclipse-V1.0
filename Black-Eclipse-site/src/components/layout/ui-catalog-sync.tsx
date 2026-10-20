'use client';

// ── Runtime catalog sync (mounted once in the app shell) ──────────────────────
// Seeds the Python UI runtime's component catalog with the REAL dashboard
// widget specs on first app load, so the agent can Compose with them without
// the user having to open the UI Builder first. Fire-and-forget and idempotent;
// the runtime persists the specs on agent-memory.db, so it is effectively a
// one-time install step.

import { useEffect } from 'react';
import { useAppShellSync } from '@/lib/sdk/app-shell-client';

export function UiCatalogSync() {
  useAppShellSync();
  useEffect(() => {
    // Everything below is background synchronization, not first-paint work:
    // the dashboard widget registry pulls the full ECharts graph, and the SDK
    // modules pull their own client. Running them in the same tick as mount
    // put that whole graph on the hydration critical path (and, in dev, made
    // the global boot overlay sit at its last percentage while those chunks
    // compiled). Wait for an idle slot so the shell becomes interactive first;
    // the fallback keeps the sync running even in browsers without idle
    // callbacks.
    const run = () => {
      // Lazy-load the sync so its dependency chain (the dashboard widget
      // registry → full ECharts) stays OUT of the initial route bundle. A
      // static import here pulled the entire ECharts library into the root `/`
      // graph, defeating the code-splitting in stock-chat.tsx and inflating dev
      // compile time and server memory.
      void import('@/lib/harness/ui-sync').then((m) => {
        void m.syncCoreCatalog();
        void m.syncAppSurfaces();
      });
      // User-created SDK widgets are runtime data, not part of the static
      // registry. Hydrate them on boot so the Pages widget library can place
      // them even if the SDK screen was never opened.
      void import('@/lib/sdk/widgets').then((m) => m.hydrateSdkWidgets());
      // Expose the typed SDK in the browser console even when no sidebar panel
      // is mounted: `eclipseSdk.widgets.create({...})`, `eclipseSdk.locks.create`.
      void import('@/lib/sdk').then(({ eclipseSdk }) => {
        (window as Window & { eclipseSdk?: typeof eclipseSdk }).eclipseSdk = eclipseSdk;
      });
    };

    // A fixed grace period (not "idle", which fires immediately during boot)
    // keeps the ECharts/SDK compile out of the first screen's way.
    const t = window.setTimeout(run, 5_000);
    return () => window.clearTimeout(t);
  }, []);
  return null;
}
