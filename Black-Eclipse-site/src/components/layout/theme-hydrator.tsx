'use client';

// ── Root theme hydrator ──────────────────────────────────────────────────────
// The saved theme (and the page-background treatment that belongs to it) has to
// reach EVERY route, not just the app shell. It used to be hydrated inside
// `StockChatContent`, so standalone routes — the consoles (`/events`, `/fabric`,
// `/recovery`, `/theses`, `/alerts`), `/terminal`, `/login`, the shared
// `/app-view` and `/figure` links — never applied the user's theme. They fell
// back to the shipped `:root` tokens, which are a GREY light palette: a white
// theme rendered as a grey page.
//
// Mounted once in `app/layout.tsx`, this applies the managed theme stylesheet
// (colour tokens + `html.dark`) and the background vars before any route paints.
// Both hooks are idempotent; the shell's existing calls are harmless duplicates.

import { useHydrateTheme } from '@/lib/theme';
import { useHydrateBackground } from '@/lib/backgrounds';

export function ThemeHydrator() {
  useHydrateTheme();
  useHydrateBackground();
  return null;
}
