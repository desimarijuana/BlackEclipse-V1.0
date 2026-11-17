// Desktop shell guards (pure predicates)
// ---------------------------------------------------------------------------
// Eclipse is a desktop application: the WebView must not fall back to the
// browser behaviours a localhost page gets for free (reload, print, save,
// page zoom, editable-area context menus, file-drop navigation, URL drag
// ghosts). `DesktopShellGuards` owns the listeners; these predicates stay
// DOM-free so they can be unit-tested in the node test environment.

/** Ctrl/Cmd chords the WebView handles as browser chrome, never as product
 *  commands. Deliberately excludes every in-app chord (K, B, `, `,`, /, Z...)
 *  and `F1..F12`, which are user-assigned sidebar navigation. */
const BROWSER_CHORDS = new Set(['r', 'p', 's', 'u', '=', '+', '-', '_', '0']);

export interface KeyLike {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
}

/** True when the chord triggers a WebView browser action (reload, print,
 *  save-page, view-source, zoom) instead of an Eclipse command. */
export function isBrowserShortcutKey(event: KeyLike): boolean {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return false;
  return BROWSER_CHORDS.has(event.key.toLowerCase());
}

/** True for inputs that own their right-click menu (undo / cut / copy /
 *  paste). Everything else is app chrome, where the WebView's default menu
 *  (Reload, Save as, Print, View source, Inspect) must not exist. */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || typeof target !== 'object') return false;
  const element = target as { tagName?: string; isContentEditable?: boolean };
  if (element.isContentEditable) return true;
  const tag = element.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
}

/** True when the drag carries OS files -- the one drag kind the WebView would
 *  otherwise use to navigate away from the app. */
export function isFileDrag(event: { dataTransfer?: { types?: ArrayLike<string> } | null }): boolean {
  const types = event.dataTransfer?.types;
  if (!types) return false;
  for (let index = 0; index < types.length; index += 1) {
    if (types[index] === 'Files') return true;
  }
  return false;
}
