"use client";

// ── In-app navigation intents ──────────────────────────────────────────────
// The shell owns the active tab (local state in `stock-chat.tsx`). Components
// that live inside dialogs need to send the operator to Strategy Studio without
// a browser reload, so they dispatch one typed window event that the shell and
// the studio screen both listen for.

import type { AppTab } from "@/lib/app-tabs";

export const NAVIGATE_EVENT = "eclipse:navigate";

export interface NavigateIntent {
  tab: AppTab;
  /** A strategy id to open once Strategy Studio is active. */
  strategy?: string;
}

// A target survives the gap between "switch tab" and "the tab's screen mounts"
// (keep-alive tabs mount lazily). The screen consumes it on mount.
let pendingStrategy: string | undefined;

export function navigateTo(intent: NavigateIntent): void {
  if (intent.strategy !== undefined) pendingStrategy = intent.strategy;
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<NavigateIntent>(NAVIGATE_EVENT, { detail: intent }));
}

export function consumeStrategyTarget(): string | undefined {
  const target = pendingStrategy;
  pendingStrategy = undefined;
  return target;
}

export function navigateToStrategy(strategyId?: string): void {
  navigateTo({ tab: "strategy-studio", strategy: strategyId });
}
