import { describe, expect, it } from 'vitest';
import { addTab, parseStoredTabs, removeTab } from './tabs';

describe('desktop tabs', () => {
  it('adds a tab once and keeps open order', () => {
    expect(addTab(['chat'], 'home')).toEqual(['chat', 'home']);
    expect(addTab(['chat', 'home'], 'home')).toEqual(['chat', 'home']);
  });

  it('closing a background tab keeps the active one', () => {
    expect(removeTab(['chat', 'home', 'news'], 'home', 'news')).toEqual({
      tabs: ['chat', 'news'],
      activeTab: 'news',
    });
  });

  it('closing the active tab activates its neighbour', () => {
    expect(removeTab(['chat', 'home', 'news'], 'home', 'home')).toEqual({
      tabs: ['chat', 'news'],
      activeTab: 'news',
    });
  });

  it('closing the right-most active tab falls back to the new last tab', () => {
    expect(removeTab(['chat', 'home'], 'home', 'home')).toEqual({
      tabs: ['chat'],
      activeTab: 'chat',
    });
  });

  it('never closes the last tab', () => {
    const tabs = ['chat'] as const;
    const result = removeTab([...tabs], 'chat', 'chat');
    expect(result.tabs).toEqual(['chat']);
    expect(result.activeTab).toBe('chat');
  });

  it('drops unknown or malformed stored tabs', () => {
    expect(parseStoredTabs('["chat","home"]')).toEqual(['chat', 'home']);
    expect(parseStoredTabs('["chat","not-a-tab",3]')).toEqual(['chat']);
    expect(parseStoredTabs('{"tabs":["chat"]}')).toEqual([]);
    expect(parseStoredTabs('not json')).toEqual([]);
    expect(parseStoredTabs(null)).toEqual([]);
  });
});
