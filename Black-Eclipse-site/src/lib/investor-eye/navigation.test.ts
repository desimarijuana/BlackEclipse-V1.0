import { describe, it, expect } from 'vitest';
import { openSettingsSection, AI_SETTINGS_SECTION } from './navigation';

describe('openSettingsSection', () => {
  it('is a safe no-op without a window (SSR / node)', () => {
    // vite config uses the node environment, so there is no window here — the
    // helper must not throw when called outside the browser.
    expect(() => openSettingsSection(AI_SETTINGS_SECTION)).not.toThrow();
  });

  it('dispatches be:navigate with the settings tab + section when a window exists', () => {
    const events: Array<{ type: string; detail: unknown }> = [];
    const fakeWindow = {
      dispatchEvent: (e: { type: string; detail?: unknown }) => {
        events.push({ type: e.type, detail: e.detail });
        return true;
      },
    };
    const g = globalThis as unknown as { window?: unknown; CustomEvent?: unknown };
    const originalWindow = g.window;
    const originalCustomEvent = g.CustomEvent;
    g.window = fakeWindow;
    // Node may not expose CustomEvent; provide a minimal one for the assertion.
    g.CustomEvent = class {
      type: string;
      detail: unknown;
      constructor(type: string, init?: { detail?: unknown }) {
        this.type = type;
        this.detail = init?.detail;
      }
    };
    try {
      openSettingsSection('ai');
    } finally {
      g.window = originalWindow;
      g.CustomEvent = originalCustomEvent;
    }
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe('be:navigate');
    expect(events[0].detail).toEqual({ tab: 'settings', section: 'ai' });
  });
});
