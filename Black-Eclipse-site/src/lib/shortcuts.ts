// ── Global shortcut catalogue ────────────────────────────────────────────────
// One list of the shortcuts that work anywhere in the app, used by the help
// dialog. Keeping the catalogue here (instead of inline in the component) makes
// the audit in one place: adding a listener means adding its row here too, and
// the dialog can warn about chords the browser reserves before the user relies
// on them.
//
// Labels are intentionally English like the per-page action labels they sit
// beside; group headings are translated. Matching stays in `lib/keyboard.ts`.

import { matchesShortcutOrCode } from './keyboard';

export type ShortcutGroupId = 'essentials' | 'navigation' | 'chart';

export interface GlobalShortcutDef {
  id: string;
  label: string;
  /** Display string (already human-formatted, platform-neutral). */
  keys: string;
  context: string;
  group: ShortcutGroupId;
  /** The browser owns this chord on some platforms, so it may not fire. */
  reserved?: boolean;
}

export const SHORTCUT_GROUP_LABEL_KEY: Record<ShortcutGroupId, string> = {
  essentials: 'keyboard.appGroup',
  navigation: 'keyboard.navGroup',
  chart: 'keyboard.chartGroup',
};

export const GLOBAL_SHORTCUTS: readonly GlobalShortcutDef[] = [
  // ── Essentials ─────────────────────────────────────────────────────────────
  {
    id: 'help',
    label: 'Keyboard shortcuts',
    keys: 'Ctrl / Cmd + /   or   ?',
    context: 'Opens this dialog. Press Escape to close it.',
    group: 'essentials',
  },
  {
    id: 'search',
    label: 'Global search & commands',
    keys: 'Ctrl / Cmd + K',
    context: 'Search pages, instruments and runnable commands.',
    group: 'essentials',
  },
  {
    id: 'focus-chat',
    label: 'Focus the chat composer',
    keys: '/',
    context: 'Works anywhere except while typing in a field.',
    group: 'essentials',
  },
  {
    id: 'chat-new',
    label: 'New chat',
    keys: 'Ctrl / Cmd + Alt + N',
    context: 'Switches to the Eclipse Agent and starts a blank conversation.',
    group: 'essentials',
  },
  {
    id: 'settings',
    label: 'Open Settings',
    keys: 'Ctrl / Cmd + ,',
    context: 'Opens the settings dialog from any screen.',
    group: 'essentials',
  },
  {
    id: 'theme',
    label: 'Toggle light / dark',
    keys: 'Ctrl / Cmd + Shift + L',
    context: 'Flips the app-wide colour scheme and remembers the choice.',
    group: 'essentials',
  },

  // ── Navigation & panels ────────────────────────────────────────────────────
  {
    id: 'sidebar-toggle',
    label: 'Collapse / expand the sidebar',
    keys: 'Ctrl / Cmd + B',
    context: 'Desktop icon rail; on phones the drawer button is used instead.',
    group: 'navigation',
  },
  {
    id: 'terminal',
    label: 'Toggle the terminal',
    keys: 'Ctrl / Cmd + `',
    context: 'Works even while the terminal or a chart has focus.',
    group: 'navigation',
  },
  {
    id: 'workspace',
    label: 'Toggle the Agent Workspace sidebar',
    keys: 'Ctrl / Cmd + Shift + E',
    context: 'The VS Code “toggle Explorer” chord.',
    group: 'navigation',
  },
  {
    id: 'mode-terminal',
    label: 'Sidebar menu: Terminal',
    keys: 'Alt + T',
    context: 'Switch the sidebar to the market tools.',
    group: 'navigation',
  },
  {
    id: 'mode-agentic',
    label: 'Sidebar menu: Agentic',
    keys: 'Alt + A',
    context: 'Switch the sidebar to the agent tools.',
    group: 'navigation',
  },
  {
    id: 'mode-bots',
    label: 'Sidebar menu: Bots',
    keys: 'Alt + B',
    context: 'Switch the sidebar and open the Bots workspace.',
    group: 'navigation',
  },
  {
    id: 'mode-graph',
    label: 'Sidebar menu: Graph Studio',
    keys: 'Alt + G',
    context: 'Switch the sidebar and open Overview.',
    group: 'navigation',
  },
  {
    id: 'focus-mode',
    label: 'Focus mode (Eclipse Agent)',
    keys: 'Ctrl + Alt + X',
    context: 'Hides the header and sidebar for a full-width chat view.',
    group: 'navigation',
  },
  {
    id: 'back',
    label: 'Back to the previous screen',
    keys: 'Alt + ←',
    context: 'Walks the in-app history; available after navigating between screens.',
    group: 'navigation',
  },
  {
    id: 'sub-tabs',
    label: 'Select a sub-tab',
    keys: 'Alt + 1…9  /  Alt + 0',
    context: 'Journal and Economics tabs; Alt + 0 picks the last tab.',
    group: 'navigation',
  },

  // ── Focused chart ──────────────────────────────────────────────────────────
  {
    id: 'chart-cancel',
    label: 'Cancel the drawing / cursor tool',
    keys: 'Escape',
    context: 'Only while a chart owns keyboard focus.',
    group: 'chart',
  },
  {
    id: 'chart-delete',
    label: 'Delete the selected drawing',
    keys: 'Delete / Backspace',
    context: 'Only while a chart owns keyboard focus.',
    group: 'chart',
  },
  {
    id: 'chart-undo',
    label: 'Undo the last drawing',
    keys: 'Ctrl / Cmd + Z',
    context: 'Only while a chart owns keyboard focus.',
    group: 'chart',
  },
  {
    id: 'chart-redo',
    label: 'Redo the last drawing',
    keys: 'Ctrl / Cmd + Shift + Z',
    context: 'Only while a chart owns keyboard focus.',
    group: 'chart',
  },
  {
    id: 'chart-volume',
    label: 'Toggle the volume pane',
    keys: 'V',
    context: 'Only while a chart owns keyboard focus.',
    group: 'chart',
  },
  {
    id: 'chart-zoom',
    label: 'Zoom / reset the chart',
    keys: '+  /  −  /  0',
    context: 'Only while a chart owns keyboard focus.',
    group: 'chart',
  },
  {
    id: 'chart-pan',
    label: 'Pan the chart',
    keys: 'Alt + ← / →',
    context: 'Only while a chart owns keyboard focus.',
    group: 'chart',
  },
];

/** Browser/OS chords a page cannot reliably intercept. Surfaced as a warning
 *  instead of a silent failure. Function-key sidebar slots use the same set. */
export const BROWSER_RESERVED_KEYS = new Set(['F1', 'F5', 'F11', 'F12']);

export function isReservedSidebarShortcut(key: string): boolean {
  return BROWSER_RESERVED_KEYS.has(key.toUpperCase());
}

type ShortcutEvent = Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey' | 'code'>;

/** Ctrl/Cmd + `/` opens help. Plain `?` (Shift + `/`) is the conventional
 *  alias and works on layouts where the slash key needs Shift. */
export function isHelpShortcut(event: ShortcutEvent): boolean {
  if (event.ctrlKey || event.metaKey) return matchesShortcutOrCode(event, 'mod+/', 'Slash');
  return !event.altKey && event.key === '?';
}

/** Ctrl/Cmd + Alt + N, with a physical-key fallback for AltGr layouts. */
export function isNewChatShortcut(event: ShortcutEvent): boolean {
  return matchesShortcutOrCode(event, 'mod+alt+n', 'KeyN');
}

/** Ctrl + Alt + X, with a physical-key fallback for AltGr layouts. */
export function isFocusModeShortcut(event: ShortcutEvent): boolean {
  return matchesShortcutOrCode(event, 'ctrl+alt+x', 'KeyX');
}

/** Ctrl/Cmd + , (Settings), with a physical-key fallback. */
export function isSettingsShortcut(event: ShortcutEvent): boolean {
  return matchesShortcutOrCode(event, 'mod+,', 'Comma');
}

/** Ctrl/Cmd + Shift + L (light/dark scheme), with a physical-key fallback. */
export function isThemeShortcut(event: ShortcutEvent): boolean {
  return matchesShortcutOrCode(event, 'mod+shift+l', 'KeyL');
}

/** Ctrl/Cmd + B (collapse/expand sidebar), with a physical-key fallback. */
export function isSidebarToggleShortcut(event: ShortcutEvent): boolean {
  return matchesShortcutOrCode(event, 'mod+b', 'KeyB');
}
