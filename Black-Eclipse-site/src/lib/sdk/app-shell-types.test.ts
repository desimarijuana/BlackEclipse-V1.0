import { describe, expect, it } from 'vitest';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import {
  APP_NAV_IDS,
  APP_NAV_SECTIONS,
  defaultAppNav,
  isAppNavMode,
  normalizeAppNav,
  parseAppShellState,
} from './app-shell-types';

describe('app shell nav contracts', () => {
  it('ships every fixed section enabled in the canonical order', () => {
    const nav = defaultAppNav();
    expect(nav.mode).toBe('terminal');
    expect(nav.sections.map((section) => section.id)).toEqual([...APP_NAV_IDS]);
    expect(nav.sections.every((section) => section.enabled)).toBe(true);
    expect(APP_NAV_SECTIONS.map((section) => section.id)).toContain('graph-studio');
  });

  it('cannot drift from the sidebar section definitions', () => {
    expect(APP_NAV_SECTIONS.map((section) => [section.id, section.group]))
      .toEqual(DEFAULT_SIDEBAR_SECTIONS.map((section) => [section.id, section.group]));
  });

  it('keeps a supplied order and visibility, dropping unknown/duplicate ids', () => {
    const nav = normalizeAppNav({
      mode: 'agentic',
      sections: [
        { id: 'sdk', enabled: true },
        { id: 'not-a-tab', enabled: true },
        { id: 'news', enabled: false },
        { id: 'sdk', enabled: false },
      ],
    });
    expect(nav.mode).toBe('agentic');
    expect(nav.sections.slice(0, 2).map((section) => section.id)).toEqual(['sdk', 'news']);
    expect(nav.sections[1].enabled).toBe(false);
    expect(nav.sections.filter((section) => section.id === 'sdk')).toHaveLength(1);
    // Missing sections are appended so the nav can never lose an entry.
    expect(nav.sections.map((section) => section.id)).toContain('dashboard');
  });

  it('inserts a newly shipped section after ChatBot instead of appending it', () => {
    const preDashboard = APP_NAV_SECTIONS
      .filter((section) => section.id !== 'home')
      .map((section) => ({ id: section.id, enabled: true }));
    const nav = normalizeAppNav({ mode: 'terminal', sections: preDashboard });
    expect(nav.sections.slice(0, 3).map((section) => section.id)).toEqual(['chat', 'home', 'dashboard']);
  });

  it('falls back on an invalid mode and non-array sections', () => {
    const nav = normalizeAppNav({ mode: 'nope', sections: 'bad' });
    expect(nav.mode).toBe('terminal');
    expect(nav.sections).toHaveLength(APP_NAV_IDS.length);
    expect(isAppNavMode('bots')).toBe(true);
    expect(isAppNavMode('everything')).toBe(false);
  });

  it('parses an uninitialized row as the shipped defaults', () => {
    const state = parseAppShellState(null);
    expect(state.initialized).toBe(false);
    expect(state.revision).toBe(0);
    expect(state.nav.sections.map((section) => section.id)).toEqual([...APP_NAV_IDS]);
  });

  it('parses a persisted revision and normalizes its nav', () => {
    const state = parseAppShellState(JSON.stringify({
      revision: 7,
      updatedAt: '2026-10-19T00:00:00.000Z',
      nav: { mode: 'agentic', sections: [{ id: 'chat', enabled: false }] },
    }));
    expect(state.initialized).toBe(true);
    expect(state.revision).toBe(7);
    expect(state.updatedAt).toBe('2026-10-19T00:00:00.000Z');
    expect(state.nav.mode).toBe('agentic');
    expect(state.nav.sections[0]).toEqual({ id: 'chat', enabled: false });
    expect(state.nav.sections).toHaveLength(APP_NAV_IDS.length);
  });

  it('treats corrupt JSON as uninitialized rather than crashing', () => {
    const state = parseAppShellState('{not json');
    expect(state.initialized).toBe(false);
    expect(state.revision).toBe(0);
  });
});
