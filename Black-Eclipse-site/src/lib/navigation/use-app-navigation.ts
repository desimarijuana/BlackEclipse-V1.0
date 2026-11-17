"use client";

// The shell owns the active tab. Dialogs (e.g. a strategy picker) dispatch a
// typed intent; this hook is the one listener that switches the tab, so the
// shell file itself stays small.

import { useEffect } from "react";
import { NAVIGATE_EVENT, type NavigateIntent } from "./app-nav";
import type { AppTab } from "@/lib/app-tabs";

export function useAppNavigation(setTab: (tab: AppTab) => void): void {
  useEffect(() => {
    const onNavigate = (event: Event) => {
      const detail = (event as CustomEvent<NavigateIntent>).detail;
      if (detail?.tab) setTab(detail.tab);
    };
    window.addEventListener(NAVIGATE_EVENT, onNavigate);
    return () => window.removeEventListener(NAVIGATE_EVENT, onNavigate);
  }, [setTab]);
}
