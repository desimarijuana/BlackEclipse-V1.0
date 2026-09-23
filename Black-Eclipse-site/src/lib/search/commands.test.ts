import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  commandShortcut,
  paramCommandFor,
  resolveCommandSymbol,
} from './commands';
import { addToWatchlist, isInWatchlist } from '@/lib/dashboard/watchlist-store';
import { defaultSidebarConfig, type SidebarConfig } from '@/lib/sidebar/config';

const cfg: SidebarConfig = defaultSidebarConfig();
const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  installWindow();
});

afterEach(() => {
  delete (globalThis as unknown as { window?: unknown }).window;
});

function installWindow() {
  (globalThis as unknown as { window: unknown }).window = {
    localStorage: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    },
    dispatchEvent: () => true,
  };
}

describe('commandShortcut', () => {
  it('returns the bound shortcut for a tab', () => {
    expect(commandShortcut('journal', cfg)).toBe('F7');
  });

  it('ignores disabled sections and returns undefined when unbound', () => {
    const disabled: SidebarConfig = {
      sections: [{ id: 'journal', enabled: false, shortcut: 'F7' }],
    };
    expect(commandShortcut('journal', disabled)).toBeUndefined();
    expect(commandShortcut('settings', disabled)).toBeUndefined();
  });
});

describe('resolveCommandSymbol', () => {
  it('resolves curated aliases to a canonical symbol', () => {
    expect(resolveCommandSymbol('aapl')).toBe('AAPL');
    expect(resolveCommandSymbol('apple')).toBe('AAPL');
    expect(resolveCommandSymbol('gold')).toBe('XAUUSD');
  });

  it('accepts a raw ticker and rejects junk', () => {
    expect(resolveCommandSymbol('ZZZZNOPE')).toBe('ZZZZNOPE');
    expect(resolveCommandSymbol('')).toBeNull();
  });
});

describe('paramCommandFor', () => {
  it('builds a watch command with a real side effect', () => {
    const cmd = paramCommandFor({ verb: 'watch', arg: 'nflx', template: '' }, cfg);
    expect(cmd?.id).toBe('cmd-watch-NFLX');
    expect(cmd?.target).toBe('NFLX');
    expect(cmd?.title).toContain('NFLX');
    expect(cmd?.destination?.tab).toBe('dashboard');
    expect(cmd?.run).toBeTypeOf('function');
    cmd?.run?.();
    expect(isInWatchlist('NFLX')).toBe(true);
  });

  it('builds a ±3% alert command pointing at the alerts tab', () => {
    const cmd = paramCommandFor({ verb: 'alert', arg: 'aapl', template: '' }, cfg);
    expect(cmd?.title).toBe('Set price alert for AAPL (±3%)');
    expect(cmd?.target).toBe('AAPL');
    expect(cmd?.destination?.tab).toBe('alerts');
    expect(cmd?.shortcut).toBe('F11');
  });

  it('builds a chart command with the symbol param', () => {
    const cmd = paramCommandFor({ verb: 'chart', arg: 'btc', template: '' }, cfg);
    expect(cmd?.destination).toEqual({ tab: 'chart', params: { symbol: 'BTC' } });
  });

  it('returns null without a usable symbol', () => {
    expect(paramCommandFor({ verb: 'watch', arg: '', template: '' }, cfg)).toBeNull();
  });
});

describe('parameterized command side effects', () => {
  it('adds a symbol to the watchlist and never duplicates it', () => {
    const cmd = paramCommandFor({ verb: 'watch', arg: 'nflx', template: '' }, cfg);
    cmd?.run?.();
    cmd?.run?.();
    expect(isInWatchlist('NFLX')).toBe(true);
    expect(addToWatchlist('NFLX')).toBeNull();
  });
});
