import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Accessibility smoke test for the locale/a11y store: the store must actually
// apply reduced-motion / high-contrast / large-text and the correct `lang`/`dir`
// to the document root. This is a dependency-free guard (no jsdom): it stubs the
// minimal DOM the store touches, mirroring `src/lib/theme/store.test.ts`.

const values = new Map<string, string>();
const storage = {
  getItem: (name: string) => values.get(name) ?? null,
  setItem: (name: string, value: string) => { values.set(name, value); },
  removeItem: (name: string) => { values.delete(name); },
};

function makeRoot() {
  const classes = new Set<string>();
  return {
    lang: '',
    dir: '',
    classList: {
      add: (c: string) => classes.add(c),
      remove: (...c: string[]) => c.forEach((x) => classes.delete(x)),
      toggle: (c: string, on?: boolean) => { if (on) classes.add(c); else classes.delete(c); },
      contains: (c: string) => classes.has(c),
    },
    _classes: classes,
  };
}

let root: ReturnType<typeof makeRoot>;

beforeEach(() => {
  vi.resetModules();
  values.clear();
  root = makeRoot();
  vi.stubGlobal('window', { localStorage: storage, addEventListener: vi.fn() });
  // The store reads the bare global `localStorage` (not `window.localStorage`).
  vi.stubGlobal('localStorage', storage);
  vi.stubGlobal('document', { documentElement: root });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function loadStore() {
  return import('./store');
}

describe('a11y / locale store applies to the document root', () => {
  it('toggling an a11y preference adds the matching document class', async () => {
    const { useLocaleStore } = await loadStore();
    useLocaleStore.getState().setA11y({ highContrast: true });
    expect(root._classes.has('a11y-high-contrast')).toBe(true);

    useLocaleStore.getState().setA11y({ highContrast: false });
    expect(root._classes.has('a11y-high-contrast')).toBe(false);
  });

  it('applies reduce-motion and large-text independently', async () => {
    const { useLocaleStore } = await loadStore();
    useLocaleStore.getState().setA11y({ reduceMotion: true, largeText: true });
    expect(root._classes.has('a11y-reduce-motion')).toBe(true);
    expect(root._classes.has('a11y-large-text')).toBe(true);
  });

  it('sets lang and dir for an RTL locale and back for LTR', async () => {
    const { useLocaleStore } = await loadStore();
    useLocaleStore.getState().setLocale('ar');
    expect(root.lang).toBe('ar');
    expect(root.dir).toBe('rtl');

    useLocaleStore.getState().setLocale('en');
    expect(root.lang).toBe('en');
    expect(root.dir).toBe('ltr');
  });

  it('persists the a11y preference so a reload re-applies it', async () => {
    const { useLocaleStore } = await loadStore();
    useLocaleStore.getState().setA11y({ highContrast: true });
    // Simulate a fresh page load: reset modules + document, then hydrate.
    vi.resetModules();
    root = makeRoot();
    vi.stubGlobal('document', { documentElement: root });
    const fresh = await loadStore();
    fresh.useLocaleStore.getState().hydrate();
    expect(root._classes.has('a11y-high-contrast')).toBe(true);
  });
});
