import { describe, expect, it } from 'vitest';
import { canHandleKeyboardEvent, hasBlockingKeyboardDialog, isKeyboardScopeVisible, matchesShortcut, preferredKeyboardScope } from './keyboard';

interface FakeEl {
  tag: string;
  attrs: Record<string, string>;
  parent: FakeEl | null;
  connected: boolean;
  ownerDoc: FakeDoc | null;
}

interface FakeDoc {
  activeElement: HTMLElement | null;
  tracked: FakeEl[];
}

function attrPartMatches(el: FakeEl, part: string): boolean {
  const tagged = part.match(/^([a-z]+)(\[.+?\])$/);
  if (tagged) {
    if (el.tag !== tagged[1]) return false;
    part = tagged[2];
  }
  if (part.startsWith('[')) {
    const attr = part.match(/^\[(.+?)(?:="(.*)")?\]$/);
    if (!attr) return false;
    const [, name, value] = attr;
    return value === undefined ? name! in el.attrs : el.attrs[name!] === value;
  }
  return el.tag === part;
}

function fakeClosest(el: FakeEl, selector: string): FakeEl | null {
  for (let node: FakeEl | null = el; node; node = node.parent) {
    if (selector.split(',').some((part) => attrPartMatches(node!, part.trim()))) return node;
  }
  return null;
}

function fakeContains(ancestor: FakeEl, node: FakeEl): boolean {
  for (let cur: FakeEl | null = node; cur; cur = cur.parent) if (cur === ancestor) return true;
  return false;
}

function asElement(fake: FakeEl): HTMLElement {
  const el = {
    get isConnected() {
      return fake.connected;
    },
    closest: (selector: string) => {
      const hit = fakeClosest(fake, selector);
      return hit ? asElement(hit) : null;
    },
    contains: (node: Node | null) => !!node && fakeContains(fake, (node as unknown as { __fake: FakeEl }).__fake),
    getClientRects: () => (fake.connected ? [{}] : []),
    isContentEditable: fake.attrs['contenteditable'] !== undefined && fake.attrs['contenteditable'] !== 'false',
    ownerDocument: fake.ownerDoc,
    getAttribute: (name: string) => fake.attrs[name] ?? null,
  };
  (el as unknown as { __fake: FakeEl }).__fake = fake;
  return el as unknown as HTMLElement;
}

function fakeDocument(): { doc: FakeDoc; el: (tag?: string, attrs?: Record<string, string>, parent?: FakeEl | null) => FakeEl } {
  const doc: FakeDoc = { activeElement: null, tracked: [] };
  const el = (tag = 'div', attrs: Record<string, string> = {}, parent: FakeEl | null = null) => {
    const fake: FakeEl = { tag, attrs, parent, connected: false, ownerDoc: doc };
    doc.tracked.push(fake);
    return fake;
  };
  return { doc, el };
}

function queryDialogs(doc: FakeDoc): HTMLElement[] {
  const selector = '[role="dialog"], [role="alertdialog"], dialog[open], [aria-modal="true"], [data-keyboard-overlay="true"]';
  return doc.tracked.filter((fake) => fake.connected && selector.split(',').some((part) => attrPartMatches(fake, part.trim()))).map(asElement);
}

function keyEvent(overrides: Record<string, unknown> = {}): KeyboardEvent {
  return {
    key: 'r',
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    repeat: false,
    defaultPrevented: false,
    isComposing: false,
    keyCode: 0,
    target: null,
    composedPath: () => [],
    ...overrides,
  } as unknown as KeyboardEvent;
}

describe('matchesShortcut', () => {
  it('matches plain character keys without modifiers', () => {
    expect(matchesShortcut(keyEvent(), 'r')).toBe(true);
    expect(matchesShortcut(keyEvent(), 'shift+e')).toBe(false);
  });

  it('normalizes mod to ctrl or meta but never both', () => {
    expect(matchesShortcut(keyEvent({ key: 'k', ctrlKey: true }), 'mod+k')).toBe(true);
    expect(matchesShortcut(keyEvent({ key: 'k', metaKey: true }), 'mod+k')).toBe(true);
    expect(matchesShortcut(keyEvent({ key: 'k', ctrlKey: true, metaKey: true }), 'mod+k')).toBe(false);
    expect(matchesShortcut(keyEvent({ key: 'k', ctrlKey: true }), 'ctrl+k')).toBe(true);
    expect(matchesShortcut(keyEvent({ key: 'k', metaKey: true }), 'ctrl+k')).toBe(false);
  });

  it('requires exact modifier sets', () => {
    expect(matchesShortcut(keyEvent({ key: 'e', shiftKey: true }), 'shift+e')).toBe(true);
    expect(matchesShortcut(keyEvent({ key: 'E', shiftKey: true }), 'shift+e')).toBe(true);
    expect(matchesShortcut(keyEvent({ key: 'e' }), 'shift+e')).toBe(false);
    expect(matchesShortcut(keyEvent({ key: 'e', altKey: true, shiftKey: true }), 'shift+e')).toBe(false);
    expect(matchesShortcut(keyEvent({ key: 'k', ctrlKey: true, shiftKey: true }), 'mod+k')).toBe(false);
  });

  it('rejects malformed key strings', () => {
    expect(matchesShortcut(keyEvent(), '')).toBe(false);
    expect(matchesShortcut(keyEvent(), '+')).toBe(false);
    expect(matchesShortcut(keyEvent({ shiftKey: true }), 'shift++')).toBe(false);
    expect(matchesShortcut(keyEvent(), 'bogus+r')).toBe(false);
    expect(matchesShortcut(keyEvent({ shiftKey: true }), 'mod+ctrl+r')).toBe(false);
  });
});

describe('preferredKeyboardScope', () => {
  it('prefers the deepest scope containing the focused element', () => {
    const { el } = fakeDocument();
    const outer = el();
    const inner = el('div', {}, outer);
    const button = el('button', {}, inner);
    const outerEl = asElement(outer);
    const innerEl = asElement(inner);
    const buttonEl = asElement(button);
    outer.connected = true;
    inner.connected = true;
    button.connected = true;
    const preferred = preferredKeyboardScope([{ root: outerEl }, { root: innerEl }], buttonEl);
    expect(preferred?.root).toBe(innerEl);
  });

  it('falls back to the deepest top-level scope when focus is outside', () => {
    const { el } = fakeDocument();
    const outer = el();
    const inner = el('div', {}, outer);
    const outerEl = asElement(outer);
    const innerEl = asElement(inner);
    const preferred = preferredKeyboardScope([{ root: outerEl }, { root: innerEl }], null);
    expect(preferred?.root).toBe(innerEl);
  });

  it('keeps the first registered scope among sibling roots', () => {
    const { el } = fakeDocument();
    const first = el();
    const second = el();
    const firstEl = asElement(first);
    const secondEl = asElement(second);
    const preferred = preferredKeyboardScope([{ root: firstEl }, { root: secondEl }], null);
    expect(preferred?.root).toBe(firstEl);
  });
});

describe('visibility and dialog guards', () => {
  it('treats disconnected or hidden roots as invisible', () => {
    const { el } = fakeDocument();
    const detached = el();
    expect(isKeyboardScopeVisible(asElement(detached))).toBe(false);
    const hiddenHost = el('div', { hidden: '' });
    const child = el('div', {}, hiddenHost);
    child.connected = true;
    hiddenHost.connected = true;
    expect(isKeyboardScopeVisible(asElement(child))).toBe(false);
    const visible = el();
    visible.connected = true;
    expect(isKeyboardScopeVisible(asElement(visible))).toBe(true);
  });

  it('blocks events when a visible dialog outside the root is open', () => {
    const { doc, el } = fakeDocument();
    const root = el();
    root.connected = true;
    const overlay = el('div', { role: 'dialog' });
    overlay.connected = true;
    doc.activeElement = asElement(el('div'));
    (doc as unknown as { queryDialogs: () => HTMLElement[] }).queryDialogs = () => queryDialogs(doc);
    const rootElement = asElement(root);
    (rootElement.ownerDocument as unknown as { querySelectorAll: (selector: string) => HTMLElement[] }).querySelectorAll = () => queryDialogs(doc);
    expect(hasBlockingKeyboardDialog(rootElement)).toBe(true);
    expect(canHandleKeyboardEvent(keyEvent(), rootElement)).toBe(false);
  });

  it('allows events when the open dialog is the root itself', () => {
    const { doc, el } = fakeDocument();
    const overlay = el('div', { role: 'dialog' });
    overlay.connected = true;
    doc.activeElement = null;
    const overlayElement = asElement(overlay);
    (overlayElement.ownerDocument as unknown as { querySelectorAll: (selector: string) => HTMLElement[] }).querySelectorAll = () => queryDialogs(doc);
    expect(canHandleKeyboardEvent(keyEvent(), overlayElement)).toBe(true);
  });

  it('blocks editable targets and focused editables', () => {
    const { doc, el } = fakeDocument();
    const root = el();
    root.connected = true;
    const rootElement = asElement(root);
    (rootElement.ownerDocument as unknown as { querySelectorAll: (selector: string) => HTMLElement[] }).querySelectorAll = () => queryDialogs(doc);
    const input = asElement(el('input'));
    expect(canHandleKeyboardEvent(keyEvent({ target: input }), rootElement)).toBe(false);
    doc.activeElement = asElement(el('textarea'));
    expect(canHandleKeyboardEvent(keyEvent(), rootElement)).toBe(false);
    doc.activeElement = asElement(el('div'));
    expect(canHandleKeyboardEvent(keyEvent(), rootElement)).toBe(true);
  });

  it('blocks repeat, composing, and defaultPrevented events', () => {
    expect(canHandleKeyboardEvent(keyEvent({ repeat: true }), null)).toBe(false);
    expect(canHandleKeyboardEvent(keyEvent({ isComposing: true }), null)).toBe(false);
    expect(canHandleKeyboardEvent(keyEvent({ defaultPrevented: true }), null)).toBe(false);
    expect(canHandleKeyboardEvent(keyEvent({ keyCode: 229 }), null)).toBe(false);
  });
});
