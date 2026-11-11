import { describe, expect, it } from 'vitest';
import {
  appendTab,
  createTab,
  moveTab,
  parseStoredTabs,
  removeTab,
  setTabPage,
  type DesktopTab,
} from './tabs';
import type { AppTab } from '@/lib/app-tabs';

const tab = (id: string, page: AppTab = 'chat'): DesktopTab => ({ id, page });

describe('desktop tabs', () => {
  it('appends tab instances, including duplicate pages', () => {
    const first = appendTab([], 'chat');
    const second = appendTab(first.tabs, 'chat');
    expect(second.tabs.map((item) => item.page)).toEqual(['chat', 'chat']);
    expect(new Set(second.tabs.map((item) => item.id)).size).toBe(2);
  });

  it('creates a tab with a stable id when given one', () => {
    expect(createTab('home', 'boot')).toEqual({ id: 'boot', page: 'home' });
  });

  it('closing a background tab keeps the active one', () => {
    expect(removeTab([tab('a'), tab('b', 'home'), tab('c', 'news')], 'b', 'c')).toEqual({
      tabs: [tab('a'), tab('c', 'news')],
      activeId: 'c',
    });
  });

  it('closing the active tab activates its neighbour', () => {
    expect(removeTab([tab('a'), tab('b', 'home'), tab('c', 'news')], 'b', 'b')).toEqual({
      tabs: [tab('a'), tab('c', 'news')],
      activeId: 'c',
    });
  });

  it('closing the right-most active tab falls back to the new last tab', () => {
    expect(removeTab([tab('a'), tab('b', 'home')], 'b', 'b')).toEqual({
      tabs: [tab('a')],
      activeId: 'a',
    });
  });

  it('never closes the last tab', () => {
    const tabs = [tab('a')];
    const result = removeTab(tabs, 'a', 'a');
    expect(result.tabs).toBe(tabs);
    expect(result.activeId).toBe('a');
  });

  it('reorders a dragged tab into the target slot', () => {
    const tabs = [tab('a'), tab('b', 'home'), tab('c', 'news')];
    expect(moveTab(tabs, 'c', 'a').map((item) => item.id)).toEqual(['c', 'a', 'b']);
    expect(moveTab(tabs, 'a', 'c').map((item) => item.id)).toEqual(['b', 'c', 'a']);
  });

  it('ignores unknown or no-op reorders', () => {
    const tabs = [tab('a'), tab('b', 'home')];
    expect(moveTab(tabs, 'a', 'a')).toBe(tabs);
    expect(moveTab(tabs, 'missing', 'b')).toBe(tabs);
  });

  it('moves the active tab when its page changes', () => {
    const tabs = [tab('a'), tab('b', 'home')];
    expect(setTabPage(tabs, 'a', 'portfolio')).toEqual([
      tab('a', 'portfolio'),
      tab('b', 'home'),
    ]);
    expect(setTabPage(tabs, 'a', 'chat')).toBe(tabs);
    expect(setTabPage(tabs, 'missing', 'chart')).toBe(tabs);
  });

  it('parses current tabs and migrates the legacy page-only list', () => {
    expect(parseStoredTabs('[{"id":"a","page":"chat"},{"id":"b","page":"home"}]')).toEqual([
      tab('a'),
      tab('b', 'home'),
    ]);
    const migrated = parseStoredTabs('["chat","home"]');
    expect(migrated.map((item) => item.page)).toEqual(['chat', 'home']);
    expect(migrated.every((item) => item.id.length > 0)).toBe(true);
  });

  it('drops unknown or malformed stored tabs', () => {
    expect(parseStoredTabs('[{"id":"a","page":"not-a-tab"},{"page":"home"},3]')).toEqual([
      { id: expect.any(String), page: 'home' },
    ]);
    expect(parseStoredTabs('{"tabs":["chat"]}')).toEqual([]);
    expect(parseStoredTabs('not json')).toEqual([]);
    expect(parseStoredTabs(null)).toEqual([]);
  });

  it('drops duplicate tab ids on restore', () => {
    expect(parseStoredTabs('[{"id":"a","page":"chat"},{"id":"a","page":"home"}]')).toEqual([
      tab('a'),
    ]);
  });
});
