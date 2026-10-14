import { beforeEach, describe, expect, it } from 'vitest';
import {
  MAX_NOTIFICATIONS,
  totalUnread,
  unreadCountsByTab,
  useNotificationsStore,
  type AppNotification,
} from './store';

function item(partial: Partial<AppNotification> & { id: string; tab: AppNotification['tab'] }): AppNotification {
  return {
    kind: 'alert',
    title: 't',
    body: 'b',
    at: 1,
    read: false,
    ...partial,
  };
}

describe('unreadCountsByTab / totalUnread', () => {
  it('counts only unread items, keyed by tab', () => {
    const items = [
      item({ id: '1', tab: 'alerts' }),
      item({ id: '2', tab: 'alerts', read: true }),
      item({ id: '3', tab: 'tasks' }),
      item({ id: '4', tab: 'chat' }),
    ];
    expect(unreadCountsByTab(items)).toEqual({ alerts: 1, tasks: 1, chat: 1 });
    expect(totalUnread(items)).toBe(3);
  });

  it('returns an empty map when everything is read', () => {
    expect(unreadCountsByTab([item({ id: '1', tab: 'news', read: true })])).toEqual({});
  });
});

describe('useNotificationsStore', () => {
  beforeEach(() => {
    useNotificationsStore.setState({ items: [], activeTab: null, hydrated: true });
  });

  it('records a pushed notification as unread and newest-first', () => {
    const store = useNotificationsStore.getState();
    expect(store.push({ id: 'a', tab: 'alerts', title: 'Alert', body: 'fired' })).toBe(true);
    store.push({ id: 'b', tab: 'tasks', title: 'Task completed', body: 'Refresh' });
    const { items } = useNotificationsStore.getState();
    expect(items.map((n) => n.id)).toEqual(['b', 'a']);
    expect(items.every((n) => !n.read)).toBe(true);
  });

  it('dedupes by id — a replayed event is not recorded twice', () => {
    const store = useNotificationsStore.getState();
    store.push({ id: 'a', tab: 'alerts', title: 'Alert', body: 'fired' });
    expect(useNotificationsStore.getState().push({ id: 'a', tab: 'alerts', title: 'Alert', body: 'fired' })).toBe(false);
    expect(useNotificationsStore.getState().items).toHaveLength(1);
  });

  it('marks a notification for the visible tab read on arrival', () => {
    useNotificationsStore.setState({ activeTab: 'chat' });
    useNotificationsStore.getState().push({ id: 'a', tab: 'chat', title: 'Approval needed', body: 'x' });
    expect(useNotificationsStore.getState().items[0].read).toBe(true);
  });

  it('markTabRead clears exactly that tab', () => {
    const store = useNotificationsStore.getState();
    store.push({ id: 'a', tab: 'alerts', title: 'Alert' });
    store.push({ id: 'b', tab: 'chat', title: 'Approval' });
    useNotificationsStore.getState().markTabRead('alerts');
    const { items } = useNotificationsStore.getState();
    expect(items.find((n) => n.tab === 'alerts')?.read).toBe(true);
    expect(items.find((n) => n.tab === 'chat')?.read).toBe(false);
  });

  it('markAllRead clears every unread item', () => {
    const store = useNotificationsStore.getState();
    store.push({ id: 'a', tab: 'alerts', title: 'Alert' });
    store.push({ id: 'b', tab: 'tasks', title: 'Task' });
    useNotificationsStore.getState().markAllRead();
    expect(totalUnread(useNotificationsStore.getState().items)).toBe(0);
  });

  it('remove drops exactly one item and leaves the rest untouched', () => {
    const store = useNotificationsStore.getState();
    store.push({ id: 'a', tab: 'alerts', title: 'Alert' });
    store.push({ id: 'b', tab: 'bots', title: 'Bot run completed' });
    useNotificationsStore.getState().remove('a');
    const { items } = useNotificationsStore.getState();
    expect(items.map((n) => n.id)).toEqual(['b']);
  });

  it('setActiveTab records the tab and clears its unread items', () => {
    const store = useNotificationsStore.getState();
    store.push({ id: 'a', tab: 'tasks', title: 'Task' });
    useNotificationsStore.getState().setActiveTab('tasks');
    expect(useNotificationsStore.getState().activeTab).toBe('tasks');
    expect(totalUnread(useNotificationsStore.getState().items)).toBe(0);
  });

  it('caps the ledger at MAX_NOTIFICATIONS, dropping the oldest', () => {
    const store = useNotificationsStore.getState();
    for (let i = 0; i < MAX_NOTIFICATIONS + 5; i++) {
      store.push({ id: `n${i}`, tab: 'news', title: `news ${i}` });
    }
    const { items } = useNotificationsStore.getState();
    expect(items).toHaveLength(MAX_NOTIFICATIONS);
    expect(items[0].id).toBe(`n${MAX_NOTIFICATIONS + 4}`);
    expect(items.some((n) => n.id === 'n0')).toBe(false);
  });
});
