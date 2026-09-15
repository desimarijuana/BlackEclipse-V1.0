'use client';

// ── WidgetConfigContext — lets a widget edit its OWN config ──────────────────
// Widgets are normally pure: they read props and report nothing back. But some
// controls belong IN the widget (e.g. "which market is this card showing?"), so
// the user doesn't have to dig into Customize → gear → panel. This context
// exposes a narrow write channel for a widget instance's own config, without
// leaking the whole workspace store.
//
// CustomizableWorkspace provides it around the canvas; widgets call
// useWidgetConfig(placement) to read their config and set it inline.

import React, { createContext, useContext } from 'react';

export interface WidgetConfigApi {
  /** Read the current config for a widget instance. */
  get: (widgetInstanceId: string) => Record<string, unknown>;
  /** Merge a partial config into a widget instance (persisted). */
  set: (widgetInstanceId: string, patch: Record<string, unknown>) => void;
}

const WidgetConfigContext = createContext<WidgetConfigApi | null>(null);

export function WidgetConfigProvider({
  value,
  children,
}: {
  value: WidgetConfigApi;
  children: React.ReactNode;
}) {
  return <WidgetConfigContext.Provider value={value}>{children}</WidgetConfigContext.Provider>;
}

/** Access the widget-config write channel (null outside a workspace). */
export function useWidgetConfigApi(): WidgetConfigApi | null {
  return useContext(WidgetConfigContext);
}
