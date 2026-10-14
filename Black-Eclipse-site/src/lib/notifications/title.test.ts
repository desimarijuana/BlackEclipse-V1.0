import { beforeEach, describe, expect, it } from 'vitest';
import { composeDocumentTitle, formatTabTitle, stripTabPrefix } from './title';
import { useNotificationsStore } from './store';

describe('formatTabTitle', () => {
  it('leaves the base title untouched when nothing is unread', () => {
    expect(formatTabTitle('BlackEclipse — AI', 0)).toBe('BlackEclipse — AI');
    expect(formatTabTitle('BlackEclipse — AI', -1)).toBe('BlackEclipse — AI');
  });

  it('prefixes the unread count', () => {
    expect(formatTabTitle('BlackEclipse — AI', 3)).toBe('(3) BlackEclipse — AI');
    expect(formatTabTitle('BlackEclipse — AI', 99)).toBe('(99) BlackEclipse — AI');
  });

  it('caps the prefix at 99+', () => {
    expect(formatTabTitle('BlackEclipse — AI', 100)).toBe('(99+) BlackEclipse — AI');
  });
});

describe('stripTabPrefix', () => {
  it('strips a numeric prefix', () => {
    expect(stripTabPrefix('(3) BlackEclipse — AI')).toBe('BlackEclipse — AI');
    expect(stripTabPrefix('(99+) BlackEclipse — AI')).toBe('BlackEclipse — AI');
  });

  it('leaves un-prefixed titles (including parenthesised names) intact', () => {
    expect(stripTabPrefix('BlackEclipse — AI')).toBe('BlackEclipse — AI');
    expect(stripTabPrefix('(Beta) BlackEclipse')).toBe('(Beta) BlackEclipse');
  });

  it('round-trips through formatTabTitle without stacking', () => {
    const once = formatTabTitle('BlackEclipse', 7);
    const twice = formatTabTitle(stripTabPrefix(once), 2);
    expect(twice).toBe('(2) BlackEclipse');
  });
});

describe('composeDocumentTitle', () => {
  beforeEach(() => {
    useNotificationsStore.setState({ items: [], activeTab: null, hydrated: true });
  });

  it('applies the ledger’s current unread count', () => {
    expect(composeDocumentTitle('BlackEclipse')).toBe('BlackEclipse');
    useNotificationsStore.getState().push({ id: 'a', tab: 'alerts', title: 'Alert' });
    useNotificationsStore.getState().push({ id: 'b', tab: 'tasks', title: 'Task' });
    expect(composeDocumentTitle('BlackEclipse')).toBe('(2) BlackEclipse');
  });
});
