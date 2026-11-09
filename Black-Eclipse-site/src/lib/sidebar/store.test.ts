import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defaultAppNav } from '@/lib/sdk/app-shell-types';
import { defaultSidebarConfig } from './config';

const shared = new Map<string, string>();
const perTab = new Map<string, string>();

vi.mock('@/lib/sdk', () => ({
  eclipseSdk: {
    app: {
      get: vi.fn(async () => ({ initialized: false })),
      update: vi.fn(async () => ({})),
    },
  },
}));

import { SIDEBAR_MODE_KEY, SIDEBAR_TAB_MODE_KEY, useSidebarConfigStore } from './store';

function storage(map: Map<string, string>): Storage {
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    clear: () => map.clear(),
    key: (index: number) => [...map.keys()][index] ?? null,
    get length() {
      return map.size;
    },
  };
}

beforeEach(() => {
  shared.clear();
  perTab.clear();
  const local = storage(shared);
  const session = storage(perTab);
  vi.stubGlobal('window', { localStorage: local, sessionStorage: session });
  vi.stubGlobal('localStorage', local);
  vi.stubGlobal('sessionStorage', session);
  useSidebarConfigStore.setState({
    config: defaultSidebarConfig(),
    hydrated: true,
    mode: 'terminal',
  });
});

describe('shortcut slots follow the default menu order', () => {
  it('re-numbers F1..F12 after a move when the user has not customized keys', () => {
    const store = useSidebarConfigStore.getState();
    expect(store.config.sections.map((s) => s.id).slice(0, 3)).toEqual(['chat', 'home', 'dashboard']);

    store.move(1, 0); // move Dashboard above ChatBot

    const moved = useSidebarConfigStore.getState().config.sections;
    expect(moved.slice(0, 3).map((s) => s.id)).toEqual(['home', 'chat', 'dashboard']);
    expect(moved.slice(0, 3).map((s) => s.shortcut)).toEqual(['F1', 'F2', 'F3']);
  });

  it('keeps a custom key attached to its tab after a move', () => {
    useSidebarConfigStore.getState().setShortcut('chat', 'F9');
    useSidebarConfigStore.getState().move(1, 0);

    const moved = useSidebarConfigStore.getState().config.sections;
    expect(moved.find((s) => s.id === 'chat')!.shortcut).toBe('F9');
    expect(useSidebarConfigStore.getState().config.shortcutsCustomized).toBe(true);
  });
});

describe('per-tab nav mode', () => {
  it('ignores the mode in a remote nav update and keeps this tab mode', () => {
    useSidebarConfigStore.setState({ mode: 'agentic' });

    useSidebarConfigStore.getState().applyRemoteState({
      revision: 2,
      initialized: true,
      updatedAt: '2026-10-19T00:00:00Z',
      nav: { ...defaultAppNav(), mode: 'bots' },
    });

    expect(useSidebarConfigStore.getState().mode).toBe('agentic');
    // The shared value is only the seed for a shell opened later.
    expect(shared.get(SIDEBAR_MODE_KEY)).toBe('bots');
  });

  it('hydrates from this tab mode before the shared seed', () => {
    shared.set(SIDEBAR_MODE_KEY, 'bots');
    perTab.set(SIDEBAR_TAB_MODE_KEY, 'agentic');

    useSidebarConfigStore.getState().hydrate();

    expect(useSidebarConfigStore.getState().mode).toBe('agentic');
  });

  it('keeps Graph mode for a tab that already chose it', () => {
    perTab.set(SIDEBAR_TAB_MODE_KEY, 'graph');

    useSidebarConfigStore.getState().hydrate();

    expect(useSidebarConfigStore.getState().mode).toBe('graph');
  });

  it('a fresh tab defaults to Terminal even when the shared seed is another mode', () => {
    shared.set(SIDEBAR_MODE_KEY, 'bots');

    useSidebarConfigStore.getState().hydrate();

    expect(useSidebarConfigStore.getState().mode).toBe('terminal');
    expect(perTab.get(SIDEBAR_TAB_MODE_KEY)).toBe('terminal');
  });

  it('persists a local mode change for this tab and as the shared seed', () => {
    useSidebarConfigStore.getState().setMode('bots');

    expect(useSidebarConfigStore.getState().mode).toBe('bots');
    expect(perTab.get(SIDEBAR_TAB_MODE_KEY)).toBe('bots');
    expect(shared.get(SIDEBAR_MODE_KEY)).toBe('bots');
  });
});
