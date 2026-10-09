import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defaultSidebarConfig, loadSidebarConfig, saveSidebarConfig, shortcutTab, DEFAULT_SIDEBAR_SECTIONS, SIDEBAR_CONFIG_KEY, navGroupsFor, modeForTab } from './config';

const memory = new Map<string, string>();

beforeEach(() => {
  memory.clear();
  vi.stubGlobal('window', {});
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => memory.get(key) ?? null,
    setItem: (key: string, value: string) => void memory.set(key, value),
    removeItem: (key: string) => void memory.delete(key),
  });
});

describe('defaultSidebarConfig', () => {
  it('assigns unique F1..F12 in canonical section order', () => {
    const config = defaultSidebarConfig();
    expect(config.shortcutVersion).toBe(2);
    // 12 shortcut slots exist; sections past the 12th get no default. This is
    // the explicit expected list — not a count derived from the source under
    // test — so adding/removing a section fails here on purpose.
    expect(config.sections.map((s) => s.shortcut)).toEqual([
      'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12', '', '', '', '',
    ]);
    expect(config.sections.map((s) => s.id)).toEqual(DEFAULT_SIDEBAR_SECTIONS.map((s) => s.id));
  });
});

describe('persistence round-trip', () => {
  it('stamps shortcutVersion 2 on save and loads it back', () => {
    const config = defaultSidebarConfig();
    config.sections[2].shortcut = 'F11';
    saveSidebarConfig(config);
    const raw = JSON.parse(memory.get(SIDEBAR_CONFIG_KEY)!);
    expect(raw.shortcutVersion).toBe(2);
    const loaded = loadSidebarConfig();
    expect(loaded.sections[2].shortcut).toBe('F11');
  });
});

describe('v1 migration', () => {
  it('adopts v2 function defaults for an untouched v1 default-order save', () => {
    const untouched = {
      sections: [
        { id: 'dashboard', enabled: true, shortcut: '' },
        { id: 'market-workspace', enabled: true, shortcut: '' },
        { id: 'chat', enabled: true, shortcut: '' },
        { id: 'discovery', enabled: true, shortcut: '' },
        { id: 'portfolio', enabled: true, shortcut: '' },
        { id: 'journal', enabled: true, shortcut: '' },
        { id: 'news', enabled: true, shortcut: '' },
        { id: 'heatmap', enabled: true, shortcut: '' },
        { id: 'economics', enabled: true, shortcut: '' },
        { id: 'alerts', enabled: true, shortcut: '' },
      ],
    };
    memory.set(SIDEBAR_CONFIG_KEY, JSON.stringify(untouched));
    // The untouched v1 legacy-order save adopts the current function defaults
    // (only the first 12 get F1..F12). This is the explicit expected list, so a
    // change to the canonical section count fails here.
    expect(loadSidebarConfig().sections.map((s) => s.shortcut)).toEqual([
      'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12', '', '', '', '',
    ]);
  });

  it('adopts v2 defaults for an untouched current-order v1 save', () => {
    memory.set(SIDEBAR_CONFIG_KEY, JSON.stringify({ sections: DEFAULT_SIDEBAR_SECTIONS.map((s) => ({ id: s.id, enabled: true, shortcut: '' })) }));
    expect(loadSidebarConfig().sections[0].shortcut).toBe('F1');
  });

  it('preserves explicit shortcuts and None through the v1→v2 upgrade', () => {
    const custom = {
      sections: [
        { id: 'chat', enabled: true, shortcut: 'F3' },
        { id: 'dashboard', enabled: true, shortcut: '' },
        { id: 'alerts', enabled: true, shortcut: 'F12' },
        { id: 'journal', enabled: false, shortcut: 'F7' },
        { id: 'news', enabled: true, shortcut: '' },
        { id: 'heatmap', enabled: true, shortcut: '' },
        { id: 'economics', enabled: true, shortcut: '' },
        { id: 'discovery', enabled: true, shortcut: '' },
        { id: 'portfolio', enabled: true, shortcut: '' },
        { id: 'market-workspace', enabled: true, shortcut: '' },
      ],
    };
    memory.set(SIDEBAR_CONFIG_KEY, JSON.stringify(custom));
    const loaded = loadSidebarConfig();
    const byId = new Map(loaded.sections.map((s) => [s.id, s]));
    expect(byId.get('chat')!.shortcut).toBe('F3');
    expect(byId.get('alerts')!.shortcut).toBe('F12');
    expect(byId.get('journal')!.shortcut).toBe('F7');
    expect(byId.get('journal')!.enabled).toBe(false);
    expect(byId.get('dashboard')!.shortcut).toBe('');
    expect(byId.get('investor-eye')!.shortcut).toBe('');
  });

  it('preserves a customized order untouched by the migration', () => {
    const reordered = {
      sections: [
        { id: 'alerts', enabled: true, shortcut: 'F1' },
        { id: 'chat', enabled: true, shortcut: '' },
        { id: 'dashboard', enabled: true, shortcut: '' },
        { id: 'market-workspace', enabled: true, shortcut: '' },
        { id: 'discovery', enabled: true, shortcut: '' },
        { id: 'portfolio', enabled: true, shortcut: '' },
        { id: 'journal', enabled: true, shortcut: '' },
        { id: 'news', enabled: true, shortcut: '' },
        { id: 'heatmap', enabled: true, shortcut: '' },
        { id: 'economics', enabled: true, shortcut: '' },
        { id: 'investor-eye', enabled: true, shortcut: '' },
      ],
    };
    memory.set(SIDEBAR_CONFIG_KEY, JSON.stringify(reordered));
    const loaded = loadSidebarConfig();
    expect(loaded.sections[0]).toEqual({ id: 'alerts', enabled: true, shortcut: 'F1' });
    expect(loaded.shortcutVersion).toBe(2);
  });

  it('drops unknown and invalid entries instead of crashing', () => {
    const messy = {
      sections: [
        { id: 'retired-tab', enabled: true, shortcut: 'F5' },
        { id: 'chat', enabled: true, shortcut: 'F99' },
        { id: 'dashboard', enabled: true, shortcut: 'F2' },
      ],
    };
    memory.set(SIDEBAR_CONFIG_KEY, JSON.stringify(messy));
    const loaded = loadSidebarConfig();
    expect(loaded.sections.slice(0, 2).map((s) => s.id)).toEqual(['chat', 'dashboard']);
    expect(loaded.sections.slice(0, 2).map((s) => s.shortcut)).toEqual(['', 'F2']);
    expect(loaded.sections).toHaveLength(DEFAULT_SIDEBAR_SECTIONS.length);
  });

  it('falls back to defaults on corrupted JSON', () => {
    memory.set(SIDEBAR_CONFIG_KEY, '{not json');
    const loaded = loadSidebarConfig();
    expect(loaded.shortcutVersion).toBe(2);
    expect(loaded.sections[0].shortcut).toBe('F1');
  });

  it('keeps a v2 save exactly as stored', () => {
    const v2 = { shortcutVersion: 2, sections: [{ id: 'chat', enabled: false, shortcut: 'F1' }] };
    memory.set(SIDEBAR_CONFIG_KEY, JSON.stringify(v2));
    const loaded = loadSidebarConfig();
    expect(loaded.sections[0]).toEqual({ id: 'chat', enabled: false, shortcut: 'F1' });
    expect(loaded.sections[1].id).toBe('dashboard');
  });
});

describe('shortcutTab', () => {
  it('returns the first enabled section bound to the key code', () => {
    const config = defaultSidebarConfig();
    expect(shortcutTab(config, 'F1')).toBe('chat');
    // Every default shortcut now maps to a section; an unassigned code is null.
    expect(shortcutTab(config, 'F11')).not.toBeNull();
    expect(shortcutTab(config, '')).toBeNull();
    const disabled = { ...config, sections: config.sections.map((s) => (s.id === 'chat' ? { ...s, enabled: false } : s)) };
    expect(shortcutTab(disabled, 'F1')).toBeNull();
  });
});

describe('nav groups (Terminal / Agentic)', () => {
  it('splits market tools into Terminal and the agent surfaces into Agentic', () => {
    const byId = new Map(DEFAULT_SIDEBAR_SECTIONS.map((s) => [s.id, s]));
    expect(navGroupsFor(byId.get('dashboard')!)).toEqual(['terminal']);
    expect(navGroupsFor(byId.get('skills')!)).toEqual(['agentic']);
    expect(navGroupsFor(byId.get('memory')!)).toEqual(['agentic']);
  });

  it('lists ChatBot in both modes', () => {
    const chat = DEFAULT_SIDEBAR_SECTIONS.find((s) => s.id === 'chat')!;
    expect(navGroupsFor(chat)).toEqual(['terminal', 'agentic']);
  });

  it('maps a tab to its mode but never forces a switch for shared ChatBot', () => {
    expect(modeForTab('news')).toBe('terminal');
    expect(modeForTab('skills')).toBe('agentic');
    expect(modeForTab('memory')).toBe('agentic');
    expect(modeForTab('chat')).toBeNull();
  });

  it('keeps ChatBot, Skills, Eclipse Memory, Artifacts, Tasks and UI Builder in the Agentic menu', () => {
    const agentic = DEFAULT_SIDEBAR_SECTIONS.filter((s) => navGroupsFor(s).includes('agentic')).map((s) => s.id);
    expect(agentic.sort()).toEqual(['artifacts', 'chat', 'memory', 'skills', 'tasks', 'ui-builder']);
  });
});
