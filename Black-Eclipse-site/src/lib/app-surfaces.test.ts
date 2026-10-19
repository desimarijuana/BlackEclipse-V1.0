import { describe, expect, it } from 'vitest';

import { APP_TABS } from './search/deep-link';
import { MEMORY_TABS, SKILLS_TABS, screenTab } from './app-screens';
import { appSurfaces } from './app-surfaces';

describe('appSurfaces', () => {
  const surfaces = appSurfaces();

  it('is complete: every AppTab has exactly one surface', () => {
    expect(surfaces.map((s) => s.id).sort()).toEqual([...APP_TABS].sort());
    expect(new Set(surfaces.map((s) => s.id)).size).toBe(APP_TABS.length);
  });

  it('exposes Memory → Reviews with its canonical deep link', () => {
    const memory = surfaces.find((s) => s.id === 'memory');
    expect(memory?.label).toBe('Eclipse Memory');
    expect(memory?.deepLink).toBe('/?tab=memory');
    expect(memory?.tabs).toContainEqual({
      id: 'memory.reviews',
      label: 'Reviews',
      deepLink: '/?tab=memory&sub=memory.reviews',
    });
  });

  it('lists every RENDERED Memory tab, not just the palette registry', () => {
    const memory = surfaces.find((s) => s.id === 'memory');
    expect(memory?.tabs).toHaveLength(15);
    expect(memory?.tabs.map((t) => t.id)).toEqual(MEMORY_TABS.map((t) => `memory.${t.id}`));
    expect(memory?.tabs).toContainEqual({
      id: 'memory.memories',
      label: 'Facts',
      deepLink: '/?tab=memory&sub=memory.memories',
    });
    expect(memory?.tabs).toContainEqual({
      id: 'memory.profiles',
      label: 'Profiles',
      deepLink: '/?tab=memory&sub=memory.profiles',
    });
  });

  it('exposes Skills → Learning Queue and the Maintenance tab', () => {
    const skills = surfaces.find((s) => s.id === 'skills');
    expect(skills?.tabs).toHaveLength(10);
    expect(skills?.tabs.map((t) => t.id)).toEqual(SKILLS_TABS.map((t) => `skills.${t.id}`));
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

  it('maps legacy subroute aliases to the rendered tab', () => {
    expect(screenTab(MEMORY_TABS, 'explorer')?.id).toBe('memories');
    expect(screenTab(MEMORY_TABS, 'learning')?.id).toBe('reviews');
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
