// ─── Typed UI intents for command results ─────────────────────────────────────
// A command can ask the CLIENT to navigate or open Canvas without embedding a
// markdown link. The intent is data, not code: non-UI surfaces (remote channels,
// CLI) ignore it, and the chat client only dispatches to the app's existing
// destination store.

import type { AppTab } from "@/lib/app-tabs";

export type CommandUiAction =
  | {
      type: "navigate";
      tab: AppTab;
      subroute?: string;
      params?: Record<string, string>;
    }
  | {
      type: "openCanvas";
      artifactId?: string;
    };
