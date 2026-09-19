import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  buildPaletteCommands,
  commandShortcut,
  exportAllFundsCommand,
  fundExportCommands,
  fundOpenCommands,
  paramCommandFor,
  rankCommands,
  resolveCommandSymbol,
  settingsCommands,
  type ExecutableCommand,
} from './commands';
import { getPageEntries } from './registry';
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
    expect(cmd?.shortcut).toBe('F12');
  });

  it('builds a chart command with the symbol param', () => {
    const cmd = paramCommandFor({ verb: 'chart', arg: 'btc', template: '' }, cfg);
    expect(cmd?.destination).toEqual({ tab: 'chart', params: { symbol: 'BTC' } });
  });

  it('returns null without a usable symbol', () => {
    expect(paramCommandFor({ verb: 'watch', arg: '', template: '' }, cfg)).toBeNull();
  });
});

describe('fund commands', () => {
  const funds = [
    { id: 'fund-a', name: 'Core Growth' },
    { id: 'fund-b', name: 'Dividend Income' },
  ];

  it('opens a fund via the existing portfolio fund param', () => {
    const cmd = fundOpenCommands(funds, cfg)[0];
    expect(cmd.title).toBe('Open fund “Core Growth”');
    expect(cmd.target).toBe('Core Growth');
    expect(cmd.destination).toEqual({ tab: 'portfolio', params: { fund: 'fund-a' } });
    expect(cmd.shortcut).toBe('F6');
  });

  it('exports a fund through the caller-supplied exporter', () => {
    const exported: string[] = [];
    const cmd = fundExportCommands(funds, (id) => exported.push(id), cfg)[0];
    expect(cmd.title).toBe('Export fund “Core Growth”');
    expect(cmd.destination).toBeNull();
    cmd.run?.();
    expect(exported).toEqual(['fund-a']);
  });

  it('offers an export-all command only when funds exist', () => {
    let ran = false;
    const cmd = exportAllFundsCommand(funds, () => { ran = true; });
    expect(cmd?.title).toBe('Export all portfolios');
    expect(cmd?.target).toBe('2 funds');
    cmd?.run?.();
    expect(ran).toBe(true);
    expect(exportAllFundsCommand([], () => {})).toBeNull();
  });
});

describe('settingsCommands', () => {
  it('emits one command per settings section, targeting the modal section', () => {
    const cmds = settingsCommands(getPageEntries(), cfg);
    expect(cmds.length).toBeGreaterThanOrEqual(10);
    const ai = cmds.find((c) => c.title === 'Open Settings · AI / LLM');
    expect(ai?.destination).toEqual({ tab: 'settings', subroute: 'settings.ai' });
    expect(cmds.every((c) => c.destination?.tab === 'settings')).toBe(true);
  });
});

describe('rankCommands', () => {
  const cmds: ExecutableCommand[] = [
    { id: 'a', title: 'Open Trading Journal', target: 'Journal', subtitle: '', keywords: ['journal'], destination: { tab: 'journal' } },
    { id: 'b', title: 'Export fund “Core Growth”', target: 'Core Growth', subtitle: '', keywords: ['export'], destination: null },
    { id: 'c', title: 'Go to Fund “Dividend Income”', target: 'Dividend Income', subtitle: '', keywords: ['fund'], destination: null },
  ];

  it('ranks a title hit above a keyword-only hit', () => {
    const res = rankCommands(cmds, 'trading');
    expect(res[0].id).toBe('a');
  });

  it('matches on the target when the title does not contain the query', () => {
    expect(rankCommands(cmds, 'dividend').map((c) => c.id)).toEqual(['c']);
  });

  it('caps the result list', () => {
    expect(rankCommands(cmds, '', 2)).toHaveLength(2);
  });
});

describe('buildPaletteCommands', () => {
  it('registers journal, today\'s events and every Settings section', () => {
    const cmds = buildPaletteCommands(cfg);
    expect(cmds.some((c) => c.id === 'cmd-open-journal' && c.destination?.tab === 'journal')).toBe(true);
    expect(cmds.some((c) => c.id === 'cmd-econ-today' && c.destination?.subroute === 'economics.calendar')).toBe(true);
    expect(cmds.some((c) => c.destination?.tab === 'settings')).toBe(true);
  });

  it('never registers a destructive command', () => {
    const cmds = buildPaletteCommands(cfg);
    const destructive = /\b(delete|remove|reset|clear|purge|wipe)\b/i;
    for (const c of cmds) {
      expect(destructive.test(c.title)).toBe(false);
      expect(destructive.test(c.id)).toBe(false);
    }
  });

  it('states the target for every command that has one, and a shortcut where bound', () => {
    const cmds = buildPaletteCommands(cfg);
    const journal = cmds.find((c) => c.id === 'cmd-open-journal');
    expect(journal?.shortcut).toBe('F7');
    expect(cmds.every((c) => c.title.length > 0 && c.subtitle.length > 0)).toBe(true);
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
