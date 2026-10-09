'use client';

// ── Runtime catalog sync (mounted once in the app shell) ──────────────────────
// Seeds the Python UI runtime's component catalog with the REAL dashboard
// widget specs on first app load, so the agent can Compose with them without
// the user having to open the UI Builder first. Fire-and-forget and idempotent;
// the runtime persists the specs on agent-memory.db, so it is effectively a
// one-time install step.

import { useEffect } from 'react';
import { syncCoreCatalog } from '@/lib/harness/ui-sync';

export function UiCatalogSync() {
  useEffect(() => {
    void syncCoreCatalog();
  }, []);
  return null;
}
