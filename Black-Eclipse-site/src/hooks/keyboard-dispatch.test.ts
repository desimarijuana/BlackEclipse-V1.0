import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { dispatchPageShortcut, useKeyboardShortcutsStore, type PageShortcut, type ShortcutScope } from './use-page-shortcuts';
import { handleSidebarShortcut, handleSidebarModeShortcut } from './use-sidebar-keybinds';
import { defaultSidebarConfig } from '@/lib/sidebar/config';
import { useSidebarConfigStore } from '@/lib/sidebar/store';
import type { AppTab } from '@/components/layout/sidebar';

function fakeRoot(attrs: Record<string, string> = {}): HTMLElement {
  return {
    isConnected: true,
    closest: () => null,
    contains: () => false,
    getClientRects: () => [{}],
    isContentEditable: false,
    getAttribute: (name: string) => attrs[name] ?? null,
    ownerDocument: { activeElement: null, querySelectorAll: () => [] },
  } as unknown as HTMLElement;
}

function keyEvent(overrides: Record<string, unknown> = {}): KeyboardEvent {
  const preventDefault = vi.fn();
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
    preventDefault,
    ...overrides,
  } as unknown as KeyboardEvent;
}

function scopeFor(root: HTMLElement, actions: readonly PageShortcut[]): ShortcutScope {
  return { token: Symbol('scope'), rootRef: { current: root }, actionsRef: { current: actions } };
}

function seedStore(scopes: readonly ShortcutScope[], extra: Partial<{ helpOpen: boolean; plainShortcutsDisabled: boolean }> = {}) {
  useKeyboardShortcutsStore.setState({ scopes, helpOpen: false, plainShortcutsDisabled: false, ...extra });
}

beforeEach(() => {
  vi.stubGlobal('window', {});
  vi.stubGlobal('document', { activeElement: null });
  useSidebarConfigStore.setState({ config: defaultSidebarConfig(), hydrated: true });
});

afterEach(() => {
  seedStore([]);
  vi.unstubAllGlobals();
});

describe('dispatchPageShortcut', () => {
  it('runs the matching action in a visible scope and prevents default', () => {
    const run = vi.fn();
    const root = fakeRoot();
    seedStore([scopeFor(root, [{ id: 'refresh', label: 'Refresh', keys: 'r', run }])]);
    const event = keyEvent();
    expect(dispatchPageShortcut(event)).toBe(true);
    expect(run).toHaveBeenCalledTimes(1);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
  });

  it('blocks while the help dialog is open', () => {
    const run = vi.fn();
    seedStore([scopeFor(fakeRoot(), [{ id: 'refresh', label: 'Refresh', keys: 'r', run }])], { helpOpen: true });
    expect(dispatchPageShortcut(keyEvent())).toBe(false);
    expect(run).not.toHaveBeenCalled();
  });

  it('blocks plain-character shortcuts when plain shortcuts are disabled', () => {
    const run = vi.fn();
    seedStore([scopeFor(fakeRoot(), [{ id: 'refresh', label: 'Refresh', keys: 'r', run }])], { plainShortcutsDisabled: true });
    expect(dispatchPageShortcut(keyEvent())).toBe(false);
    expect(run).not.toHaveBeenCalled();
    const run2 = vi.fn();
    seedStore([scopeFor(fakeRoot(), [{ id: 'undo', label: 'Undo', keys: 'mod+z', run: run2 }])], { plainShortcutsDisabled: true });
    expect(dispatchPageShortcut(keyEvent({ key: 'z', ctrlKey: true }))).toBe(true);
    expect(run2).toHaveBeenCalledTimes(1);
  });

  it('ignores disabled actions and unmatched keys', () => {
    const run = vi.fn();
    seedStore([scopeFor(fakeRoot(), [{ id: 'refresh', label: 'Refresh', keys: 'r', run, enabled: false }])]);
    expect(dispatchPageShortcut(keyEvent())).toBe(false);
    expect(run).not.toHaveBeenCalled();
  });

  it('ignores disconnected roots', () => {
    const run = vi.fn();
    const root = fakeRoot();
    (root as unknown as { isConnected: boolean }).isConnected = false;
    seedStore([scopeFor(root, [{ id: 'refresh', label: 'Refresh', keys: 'r', run }])]);
    expect(dispatchPageShortcut(keyEvent())).toBe(false);
    expect(run).not.toHaveBeenCalled();
  });

  it('prefers the focused deepest scope for a shared key', () => {
    const outerRun = vi.fn();
    const innerRun = vi.fn();
    const outer = fakeRoot();
    const inner = fakeRoot();
    (outer as unknown as { contains: (n: unknown) => boolean }).contains = (n) => n === inner || n === outer;
    (inner as unknown as { contains: (n: unknown) => boolean }).contains = (n) => n === inner;
    seedStore([scopeFor(outer, [{ id: 'a', label: 'A', keys: 'shift+w', run: outerRun }]), scopeFor(inner, [{ id: 'b', label: 'B', keys: 'shift+w', run: innerRun }])]);
    vi.stubGlobal('document', { activeElement: inner });
    expect(dispatchPageShortcut(keyEvent({ key: 'w', shiftKey: true }))).toBe(true);
    expect(innerRun).toHaveBeenCalledTimes(1);
    expect(outerRun).not.toHaveBeenCalled();
  });
});

describe('handleSidebarShortcut', () => {
  it('navigates to the F2 tab per the shipped v2 defaults', () => {
    const navigated: AppTab[] = [];
    const event = keyEvent({ key: 'F2' });
    expect(handleSidebarShortcut(event, defaultSidebarConfig(), (tab) => navigated.push(tab))).toBe(true);
    expect(navigated).toEqual(['home']);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
  });

  it('rejects modified function keys before any guard runs', () => {
    const navigated: AppTab[] = [];
    expect(handleSidebarShortcut(keyEvent({ key: 'F2', shiftKey: true }), defaultSidebarConfig(), (tab) => navigated.push(tab))).toBe(false);
    expect(navigated).toEqual([]);
  });

  it('does nothing when the key has no assignment', () => {
    const navigated: AppTab[] = [];
    const config = defaultSidebarConfig();
    config.sections = config.sections.map((s) => ({ ...s, shortcut: '' }));
    expect(handleSidebarShortcut(keyEvent({ key: 'F2' }), config, (tab) => navigated.push(tab))).toBe(false);
    expect(navigated).toEqual([]);
  });
});

describe('handleSidebarModeShortcut', () => {
  it('switches to Agentic on Alt+A and back to Terminal on Alt+T', () => {
    useSidebarConfigStore.setState({ mode: 'terminal' });
    expect(handleSidebarModeShortcut(keyEvent({ key: 'a', altKey: true }))).toBe(true);
    expect(useSidebarConfigStore.getState().mode).toBe('agentic');
    expect(handleSidebarModeShortcut(keyEvent({ key: 't', altKey: true }))).toBe(true);
    expect(useSidebarConfigStore.getState().mode).toBe('terminal');
  });

  it('switches to Bots on Alt+B', () => {
    useSidebarConfigStore.setState({ mode: 'terminal' });
    expect(handleSidebarModeShortcut(keyEvent({ key: 'b', altKey: true }))).toBe(true);
    expect(useSidebarConfigStore.getState().mode).toBe('bots');
  });

  it('ignores the plain key without the Alt modifier', () => {
    useSidebarConfigStore.setState({ mode: 'terminal' });
    expect(handleSidebarModeShortcut(keyEvent({ key: 'a' }))).toBe(false);
    expect(useSidebarConfigStore.getState().mode).toBe('terminal');
  });

  it('does nothing while the help dialog is open', () => {
    useSidebarConfigStore.setState({ mode: 'terminal' });
    seedStore([], { helpOpen: true });
    expect(handleSidebarModeShortcut(keyEvent({ key: 'a', altKey: true }))).toBe(false);
    expect(useSidebarConfigStore.getState().mode).toBe('terminal');
  });
});
