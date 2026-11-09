import { describe, expect, it } from 'vitest';

import { APP_TABS } from './search/deep-link';
import { MEMORY_TABS, SKILLS_GROUPS, SKILLS_TABS, screenTab } from './app-screens';
import { appSurfaces } from './app-surfaces';

describe('appSurfaces', () => {
  const surfaces = appSurfaces();

  it('is complete: every AppTab has exactly one surface', () => {
    expect(surfaces.map((s) => s.id).sort()).toEqual([...APP_TABS].sort());
    expect(new Set(surfaces.map((s) => s.id)).size).toBe(APP_TABS.length);
  });

  it('exposes Memory → Review with its canonical deep link', () => {
    const memory = surfaces.find((s) => s.id === 'memory');
    expect(memory?.label).toBe('Eclipse Memory');
    expect(memory?.deepLink).toBe('/?tab=memory');
    expect(memory?.tabs).toContainEqual({
      id: 'memory.review',
      label: 'Review',
      deepLink: '/?tab=memory&sub=memory.review',
    });
  });

  it('lists every RENDERED Memory tab, not just the palette registry', () => {
    const memory = surfaces.find((s) => s.id === 'memory');
    expect(memory?.tabs).toHaveLength(MEMORY_TABS.length);
    expect(memory?.tabs.map((t) => t.id)).toEqual(MEMORY_TABS.map((t) => `memory.${t.id}`));
    expect(memory?.tabs).toContainEqual({
      id: 'memory.preferences',
      label: 'Preferences',
      deepLink: '/?tab=memory&sub=memory.preferences',
    });
    expect(memory?.tabs).toContainEqual({
      id: 'memory.facts',
      label: 'Facts',
      deepLink: '/?tab=memory&sub=memory.facts',
    });
    expect(memory?.tabs).toContainEqual({
      id: 'memory.settings',
      label: 'Settings',
      deepLink: '/?tab=memory&sub=memory.settings',
    });
  });

  it('exposes Skills → Learning Queue and the Maintenance tab', () => {
    const skills = surfaces.find((s) => s.id === 'skills');
    const visible = SKILLS_TABS.filter((t) => !t.hidden);
    expect(skills?.tabs).toHaveLength(visible.length);
    expect(skills?.tabs.map((t) => t.id)).toEqual(visible.map((t) => `skills.${t.id}`));
    // Start Here became first-run content; it stays deep-linkable but is not a tab.
    expect(skills?.tabs.map((t) => t.id)).not.toContain('skills.start');
    expect(skills?.tabs).toContainEqual({
      id: 'skills.learning',
      label: 'Learning Queue',
      deepLink: '/?tab=skills&sub=skills.learning',
    });
    expect(skills?.tabs).toContainEqual({
      id: 'skills.maintenance',
      label: 'Maintenance',
      deepLink: '/?tab=skills&sub=skills.maintenance',
    });
  });

  it('groups every visible Skills tab under one of five primary destinations', () => {
    const visible = SKILLS_TABS.filter((t) => !t.hidden).map((t) => t.id);
    const grouped = SKILLS_GROUPS.flatMap((g) => g.tabs).filter((id) => visible.includes(id));
    expect(SKILLS_GROUPS).toHaveLength(5);
    expect(new Set(grouped)).toEqual(new Set(visible));
  });

  it('maps legacy subroute aliases to the rendered tab', () => {
    expect(screenTab(MEMORY_TABS, 'explorer')?.id).toBe('facts');
    expect(screenTab(MEMORY_TABS, 'learning')?.id).toBe('review');
    expect(screenTab(SKILLS_TABS, 'maintenance')?.id).toBe('maintenance');
    expect(screenTab(SKILLS_TABS, 'nope')).toBeUndefined();
  });

  it('gives every sub-tab a unique id and a tab+sub deep link', () => {
    for (const surface of surfaces) {
      const ids = surface.tabs.map((t) => t.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const tab of surface.tabs) {
        expect(tab.deepLink).toBe(`/?tab=${surface.id}&sub=${tab.id}`);
      }
    }
  });

  it('always has a human-readable label and a deep link per screen', () => {
    for (const surface of surfaces) {
      expect(surface.label.trim().length).toBeGreaterThan(0);
      expect(surface.deepLink).toBe(`/?tab=${surface.id}`);
    }
  });
});
