import { describe, expect, it } from 'vitest';
import { LABS, MODE_TABS, TAB_META } from './mobile-bottom-nav';

// ── The coverage guard that a blank page taught us ─────────────────────────
// The bar renders `TAB_META[id].icon` for every tab a mode lists. `TAB_META` was
// typed `Record<string, …>`, so adding `graph-studio` to a mode WITHOUT adding
// its meta compiled fine and then threw `Cannot read properties of undefined
// (reading 'icon')` on render — and because the chosen sidebar mode is
// persisted, EVERY subsequent page load hit the same crash inside the top-level
// ErrorBoundary: the app appeared to not load at all.
//
// These assertions make that class of bug fail in tests instead of in the shell.

describe('mobile bottom nav — tab metadata coverage', () => {
  it('every tab listed by every mode has an icon entry', () => {
    const missing: string[] = [];
    for (const [mode, tabs] of Object.entries(MODE_TABS)) {
      for (const tab of tabs) {
        if (!TAB_META[tab]?.icon) missing.push(`${mode}:${tab}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it('every lab tile has an icon entry', () => {
    expect(LABS.filter((id) => !TAB_META[id]?.icon)).toEqual([]);
  });

  it('the graph mode opens the overview workspace below ChatBot', () => {
    expect(MODE_TABS.graph.slice(0, 2)).toEqual(['chat', 'overview']);
    expect(TAB_META.overview?.icon).toBeDefined();
  });

  it('lists no tab twice inside a mode', () => {
    for (const [mode, tabs] of Object.entries(MODE_TABS)) {
      expect(new Set(tabs).size, mode).toBe(tabs.length);
    }
  });
});
