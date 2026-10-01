const MODIFIERS = ['mod', 'ctrl', 'meta', 'alt', 'shift'];

type KeyboardModifiers = Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'>;

export function matchesShortcut(event: KeyboardModifiers, keys: string): boolean {
  const parts = keys.toLowerCase().split('+').map((part) => part.trim());
  const key = parts.pop();
  if (!key || parts.some((part) => !part || !MODIFIERS.includes(part))) return false;
  const modifiers = new Set(parts);
  if (modifiers.size !== parts.length) return false;
  if (modifiers.has('mod') && (modifiers.has('ctrl') || modifiers.has('meta'))) return false;
  const primary = modifiers.has('mod')
    ? !!event.ctrlKey !== !!event.metaKey
    : !!event.ctrlKey === modifiers.has('ctrl') && !!event.metaKey === modifiers.has('meta');
  return primary && !!event.altKey === modifiers.has('alt') && !!event.shiftKey === modifiers.has('shift') && event.key.toLowerCase() === key;
}

const MODIFIER_LABELS: Record<string, string> = {
  mod: 'Ctrl / Cmd',
  ctrl: 'Ctrl',
  meta: 'Cmd',
  alt: 'Alt',
  shift: 'Shift',
};

/**
 * A human-readable label for a shortcut spec (`mod+n` -> `Ctrl / Cmd + N`,
 * `shift+e` -> `Shift + E`). A bare key is uppercased; a malformed spec is
 * returned unchanged. Display only — matching uses `matchesShortcut`.
 */
export function formatShortcutKeys(keys: string): string {
  const trimmed = (keys || '').trim();
  if (!trimmed || !trimmed.includes('+')) return trimmed.toUpperCase();
  return trimmed
    .split('+')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => MODIFIER_LABELS[part.toLowerCase()] ?? part.toUpperCase())
    .join(' + ');
}

export function isKeyboardScopeVisible(root: HTMLElement | null): boolean {
  if (!root || !root.isConnected || typeof root.closest !== 'function') return false;
  if (root.closest('[hidden], [inert], [aria-hidden="true"], [data-closed]')) return false;
  if (typeof root.getClientRects !== 'function' || root.getClientRects().length === 0) return false;
  const style = root.ownerDocument?.defaultView?.getComputedStyle?.(root);
  return !style || (style.visibility !== 'hidden' && style.visibility !== 'collapse' && style.display !== 'none');
}

const DIALOG_SELECTOR = '[role="dialog"], [role="alertdialog"], dialog[open], [aria-modal="true"], [data-keyboard-overlay="true"]';

export function hasBlockingKeyboardDialog(root?: HTMLElement | null): boolean {
  const doc = root?.ownerDocument ?? (typeof document !== 'undefined' ? document : null);
  if (!doc || typeof doc.querySelectorAll !== 'function') return false;
  return Array.from(doc.querySelectorAll<HTMLElement>(DIALOG_SELECTOR)).some(
    (dialog) => isKeyboardScopeVisible(dialog) && !(root && dialog.contains(root)),
  );
}

const EDITABLE_SELECTOR = 'input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"], [role="textbox"], [role="combobox"]';

function isEditableElement(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element || typeof element.closest !== 'function') return false;
  return element.isContentEditable === true || !!element.closest(EDITABLE_SELECTOR);
}

export function isKeyboardEventAvailable(event: KeyboardEvent): boolean {
  return !event.defaultPrevented && !event.repeat && event.isComposing !== true && event.keyCode !== 229;
}

export function canHandleKeyboardEvent(event: KeyboardEvent, root?: HTMLElement | null): boolean {
  if (!isKeyboardEventAvailable(event)) return false;
  if (root !== undefined && !isKeyboardScopeVisible(root)) return false;
  const doc = root?.ownerDocument ?? (typeof document !== 'undefined' ? document : null);
  if (!doc) return false;
  const active = doc.activeElement as HTMLElement | null;
  if (isEditableElement(event.target) || (active && isEditableElement(active))) return false;
  if (typeof event.composedPath === 'function' && event.composedPath().some(isEditableElement)) return false;
  return !hasBlockingKeyboardDialog(root);
}

export function preferredKeyboardScope<T extends { root: HTMLElement }>(scopes: readonly T[], focused: Element | null): T | undefined {
  const focusedScopes = scopes.filter(({ root }) => focused && root.contains(focused));
  return (focusedScopes.length ? focusedScopes : scopes).reduce<T | undefined>((best, candidate) => {
    if (!best || best.root.contains(candidate.root)) return candidate;
    return best;
  }, undefined);
}
