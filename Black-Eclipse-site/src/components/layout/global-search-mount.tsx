'use client';

// ── GlobalSearchMount — the lightweight, always-present half of the command ──
// center. Mounted once in the root layout. It owns ONLY the global keybinds
// (Ctrl/Cmd+K toggles the palette, plain `/` focuses the chat composer) and
// lazily loads the heavy overlay (`GlobalSearchOverlay` — the palette UI plus
// the search library) as a separate chunk.
//
// The layout previously imported the whole overlay statically, so all of it sat
// on the initial bundle of EVERY route. The keybinds are tiny, so splitting them
// out keeps the shortcuts working on the first keypress while the overlay loads
// off the critical path.

import dynamic from 'next/dynamic';
import { useCommandStore } from '@/lib/search/store';
import { useCommandCenterKeybind } from '@/hooks/use-command-center-keybind';
import { useChatFocusKeybind } from '@/hooks/use-chat-focus-keybind';

const GlobalSearchOverlay = dynamic(
  () => import('./global-search').then((m) => m.GlobalSearchOverlay),
  { ssr: false },
);

export function GlobalSearchMount() {
  const open = useCommandStore((s) => s.open);
  const toggle = useCommandStore((s) => s.toggle);

  // Ctrl/Cmd+K opens the command center; the two shortcuts never overlap with
  // plain `/`, which focuses the chat composer.
  useCommandCenterKeybind({ open, onToggle: toggle });
  // Mounted once with the command center (which lives in the root layout), so
  // `/` reaches the composer on every route, including the standalone pages.
  useChatFocusKeybind();

  // Render the overlay ONLY when open. Rendering it unconditionally downloaded
  // the palette library on every route (the root layout mounts this), and
  // prewarming it at idle still put that compile on the boot path. The keybinds
  // are local, so the first Ctrl+K loads the chunk on demand.
  return open ? <GlobalSearchOverlay /> : null;
}
