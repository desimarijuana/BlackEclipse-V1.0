// The desktop launcher runs outside the Next app, but its progress page is the
// only thing a user sees between clicking the icon and the app appearing, so it
// gets the same test treatment: the inline script must parse, it must render the
// user's saved theme (not a hard-coded palette), the status lifecycle must be
// honest, and a splash page must only be re-used when its launcher is alive.

import { createRequire } from 'node:module';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const scripts = path.join(process.cwd(), 'scripts', 'lib');
const splashModule = require(path.join(scripts, 'desktop-splash.js')) as {
  PAGE: string;
  renderPage: (theme: Record<string, unknown>) => string;
  themeCss: (theme: Record<string, unknown>) => string;
  createSplash: (options: Record<string, unknown>) => Promise<{
    port: number;
    url: string;
    state: Record<string, unknown>;
    update: (patch: Record<string, unknown>) => void;
    ready: (url?: string) => void;
    fail: (message: string, detail?: string) => void;
    close: () => void;
    closed: boolean;
    theme: Record<string, unknown>;
  } | null>;
  findSplash: (options: Record<string, unknown>) => Promise<{ port: number; url: string; state: Record<string, unknown> } | null>;
};
const themeModule = require(path.join(scripts, 'app-theme.js')) as {
  DEFAULT_THEME: Record<string, unknown>;
  sanitizeTheme: (raw: unknown) => Record<string, any>;
  readTheme: () => Record<string, any>;
};

const opened: Array<{ close: () => void }> = [];

afterEach(() => {
  for (const splash of opened.splice(0)) splash.close();
});

function basePort(): number {
  // High, uncommon, and different per run so a leftover page cannot collide.
  return 3400 + Math.floor(Math.random() * 120);
}

async function status(url: string) {
  const response = await fetch(`${url}status`, { cache: 'no-store' });
  return (await response.json()) as Record<string, unknown> & {
    ready?: boolean;
    error?: { message: string } | null;
    tail?: string;
  };
}

describe('desktop splash page', () => {
  it('ships an inline script that parses', () => {
    const script = splashModule.PAGE.match(/<script>([\s\S]*?)<\/script>/);
    expect(script).not.toBeNull();
    expect(() => new Function(script![1])).not.toThrow();
  });

  it('renders the shipped theme by default and uses the real brand assets', () => {
    const html = splashModule.renderPage(themeModule.sanitizeTheme(themeModule.DEFAULT_THEME));
    expect(html).not.toMatch(/https?:\/\//);
    expect(html).toContain('src="/logo"');
    expect(html).toContain('href="/favicon"');
    expect(html).toContain('#7aff78');
    expect(html).toContain('#34d399');
    expect(html).not.toContain('-webkit-backdrop-filter');
    // No status chip: the page shows the phase only.
    expect(html).not.toContain('Booting');
  });

  it('honours the user’s saved theme (colors, scheme, radius, glass)', () => {
    const theme = themeModule.sanitizeTheme({
      appName: 'Eclipse Desk',
      scheme: 'light',
      colors: {
        primary: '#b4ff42',
        accent: '#c9ff77',
        background: '#f6f6f7',
        surface: '#ffffff',
        border: '#e4e4e7',
        text: '#18181b',
      },
      radius: 1,
      logoScale: 1.5,
      glass: { enabled: false, blur: 0, opacity: 0.62, tint: '#ffffff' },
      shadow: 'none',
      background: 'grid',
      glow: false,
    });

    expect(theme.source).toBe('db');
    expect(theme.primaryRgb).toBe('180 255 66');

    const css = splashModule.themeCss(theme);
    expect(css).toContain('--brand: #b4ff42');
    expect(css).toContain('--brand-accent: #c9ff77');
    expect(css).toContain('--bg: #f6f6f7');
    expect(css).toContain('--radius: 1rem');
    expect(css).toContain('--logo-height: 34.5px');
    expect(css).toContain('--card-blur: none');
    expect(css).toContain('--grid-alpha: 0.045');
    expect(css).toContain('--glow-alpha: 0');

    const html = splashModule.renderPage(theme);
    // Light scheme drops the `dark` class, so the light-only rules apply.
    expect(html).toContain('<html lang="en" class="">');
    expect(html).toContain('Eclipse Desk');
    expect(html).toContain('light');
  });

  it('sanitizes theme values before they reach CSS or HTML', function () {
    const theme = themeModule.sanitizeTheme({
      appName: '<img src=x onerror=alert(1)>Desk',
      scheme: 'neon',
      colors: { primary: 'red; background:url(javascript:1)', accent: '#abc' },
      fontUi: 'Arial; }</style><script>alert(1)</script>',
      fontMono: 'Menlo, monospace',
      radius: 99,
      glass: { enabled: true, blur: -5, opacity: 10, tint: 'not-a-color' },
      background: 'lava',
      logoUrl: 'https://evil.example/logo.svg',
      faviconUrl: '/branding/FAVICON.svg',
    });

    expect(theme.appName).not.toContain('<');
    expect(theme.scheme).toBe('dark');
    expect(theme.colors.primary).toBe('#7aff78');
    expect(theme.colors.accent).toBe('#aabbcc');
    expect(theme.fontUi).not.toContain('<');
    expect(theme.fontUi).not.toContain('}');
    expect(theme.fontMono).toBe('Menlo, monospace');
    expect(theme.radius).toBe(2);
    expect(theme.glass.blur).toBe(0);
    expect(theme.glass.opacity).toBe(0.95);
    expect(theme.background).toBe('solid');
    expect(theme.logoUrl).toBe('');
    expect(theme.faviconUrl).toBe('/branding/FAVICON.svg');
  });

  it('serves the logo and favicon from the theme (shipped files by default)', async () => {
    const splash = await splashModule.createSplash({ port: basePort(), tries: 4, url: 'http://x/' });
    opened.push(splash!);

    for (const [route, marker] of [
      ['logo', 'viewBox="0 0 124 32"'],
      ['favicon', 'viewBox="0 0 32 32"'],
    ] as const) {
      const response = await fetch(`${splash!.url}${route}`);
      expect(response.status).toBe(200);
      expect(response.headers.get('content-type')).toContain('image/svg+xml');
      const body = await response.text();
      expect(body.toLowerCase()).toContain('<svg');
      expect(body).toContain(marker);
    }
  });

  it('reports phases, then ready, then a failure', async () => {
    const splash = await splashModule.createSplash({
      port: basePort(),
      tries: 4,
      url: 'http://127.0.0.1:3100/?desktop=1',
      logPath: 'launcher.log',
      serverLogPath: 'server.log',
    });
    expect(splash).not.toBeNull();
    opened.push(splash!);

    let state = await status(splash!.url);
    expect(state.phase).toBe('preparing');

    splash!.update({ phase: 'building', detail: 'Building the production bundle…' });
    state = await status(splash!.url);
    expect(state.phase).toBe('building');
    expect(state.detail).toBe('Building the production bundle…');

    splash!.ready('https://blackeclipse/?desktop=1');
    state = await status(splash!.url);
    expect(state.ready).toBe(true);
    expect(state.url).toBe('https://blackeclipse/?desktop=1');

    // A failed boot must surface a reason, not a spinner that never ends.
    splash!.fail('The build did not finish.', 'line one\nline two');
    state = await status(splash!.url);
    expect(state.ready).not.toBe(true);
    expect(state.error?.message).toBe('The build did not finish.');
    expect(state.tail).toContain('line two');
  });

  it('only re-uses a splash page whose launcher is alive', async () => {
    const port = basePort();
    const splash = await splashModule.createSplash({ port, tries: 4, url: 'http://x/' });
    opened.push(splash!);

    const live = await splashModule.findSplash({
      port,
      tries: 4,
      pidAlive: (pid: number) => pid === process.pid,
    });
    expect(live?.url).toBe(splash!.url);

    const dead = await splashModule.findSplash({ port, tries: 4, pidAlive: () => false });
    expect(dead).toBeNull();
  });

  it('reads the real app-wide theme from JDDS (and falls back safely)', () => {
    // In CI there may be no theme row; either way the shape is complete.
    const theme = themeModule.readTheme();
    expect(['db', 'default']).toContain(theme.source);
    expect(theme.colors.primary).toMatch(/^#[0-9a-f]{6}$/);
    expect(['dark', 'light']).toContain(theme.scheme);
    expect(typeof theme.appName).toBe('string');
  });
});
