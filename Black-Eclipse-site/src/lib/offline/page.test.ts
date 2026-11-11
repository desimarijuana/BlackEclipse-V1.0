import { describe, expect, it } from 'vitest';
import { DEFAULT_ECLIPSE_THEME, normalizeTheme } from '@/lib/theme/tokens';
import { renderOfflinePage } from './page';

const WORDMARK = '<svg viewBox="0 0 10 10"><path d="M0 0h10v10H0z"/></svg>';

describe('renderOfflinePage', () => {
  it('renders the app name, the honest status and the restart command', () => {
    const html = renderOfflinePage({ theme: DEFAULT_ECLIPSE_THEME, wordmark: WORDMARK });
    expect(html).toContain('BlackEclipse is offline');
    expect(html).toContain('black eclipse');
    expect(html).toContain('Looking for BlackEclipse');
    // It must say the server stopped, not pretend the user is offline.
    expect(html).toContain('local server has simply stopped');
  });

  it('is self-contained: no external stylesheet, script or image request', () => {
    const html = renderOfflinePage({ theme: DEFAULT_ECLIPSE_THEME, wordmark: WORDMARK });
    expect(html).not.toMatch(/<(link|script)[^>]+(src|href)="https?:/i);
    expect(html).not.toMatch(/<img[^>]+src="https?:/i);
    expect(html).not.toContain('@import');
    // The wordmark is inlined, so the page paints with nothing listening.
    expect(html).toContain('<svg viewBox="0 0 10 10">');
  });

  it('paints with the saved app-wide theme, not a hardcoded palette', () => {
    const theme = normalizeTheme({
      ...DEFAULT_ECLIPSE_THEME,
      scheme: 'light',
      colors: { ...DEFAULT_ECLIPSE_THEME.colors, primary: '#2266ff', background: '#fafafa' },
    });
    const html = renderOfflinePage({ theme, wordmark: WORDMARK });
    expect(html).toContain('--primary: #2266ff;');
    expect(html).toContain('--background: #fafafa;');
    expect(html).toContain('class="light"');
    expect(html).not.toContain('class="dark"');
  });

  it('escapes the app name and never emits a stylesheet-breaking CSS value', () => {
    const theme = {
      ...DEFAULT_ECLIPSE_THEME,
      appName: '<script>alert(1)</script>',
      fontUi: 'Inter; } body { display:none }',
    };
    const html = renderOfflinePage({ theme, wordmark: WORDMARK });
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(html).not.toContain('display:none');
  });

  it('reconnects by itself, offers a manual retry, and can start the app', () => {
    const html = renderOfflinePage({ theme: DEFAULT_ECLIPSE_THEME, wordmark: WORDMARK });
    expect(html).toContain("fetch('/branding/FAVICON.svg?probe='");
    expect(html).toContain("location.replace('/')");
    expect(html).toContain('id="retry"');
    expect(html).toContain('Start BlackEclipse</button>');
    // The button asks the always-on front door to boot the app.
    expect(html).toContain("fetch('/__eclipse/start'");
    expect(html).toContain("'x-eclipse-control': '1'");
  });

  it('falls back to a monogram badge when no wordmark is supplied', () => {
    const html = renderOfflinePage({ theme: DEFAULT_ECLIPSE_THEME });
    expect(html).toContain('class="logo-mono"');
  });
});
