import { describe, expect, it } from 'vitest';
import {
  INTERACTIVE_CSP,
  composeInteractiveDocument,
  jsonForScript,
} from './document';

describe('interactive document composer', () => {
  it('delivers an immutable CSP that blocks all network access', () => {
    const html = composeInteractiveDocument({ html: '<p>x</p>', nonce: 'n1' });
    expect(html).toContain('http-equiv="Content-Security-Policy"');
    expect(html).toContain("default-src 'none'");
    expect(html).toContain("connect-src 'none'");
    expect(html).toContain("script-src 'unsafe-inline'");
    expect(INTERACTIVE_CSP).not.toContain("'self'");
  });

  it('injects the runtime before the widget script', () => {
    const html = composeInteractiveDocument({
      html: '<div id="root"></div>',
      js: 'window.__widgetMarker = true;',
      nonce: 'n2',
    });
    expect(html.indexOf('window.Eclipse=')).toBeGreaterThan(-1);
    expect(html.indexOf('window.Eclipse=')).toBeLessThan(html.indexOf('__widgetMarker'));
    expect(html).toContain('eclipse:ready');
  });

  it('escapes a closing script tag inside widget JS', () => {
    const html = composeInteractiveDocument({
      html: '<p>x</p>',
      js: 'const s = "</script><img src=x onerror=alert(1)>";',
      nonce: 'n3',
    });
    expect(html).not.toContain('</script><img');
    expect(html).toContain('<\\/script>');
  });

  it('escapes HTML-breaking characters in static data', () => {
    const html = composeInteractiveDocument({
      html: '<p>x</p>',
      data: { payload: '</script><script>alert(1)</script>' },
      nonce: 'n4',
    });
    expect(html).toContain('\\u003c/script\\u003e');
    expect(html).not.toContain('</script><script>alert(1)');
  });

  it('keeps a full document body, styles and scripts, but owns the CSP', () => {
    const html = composeInteractiveDocument({
      html:
        '<!doctype html><html><head><title>evil</title>' +
        '<meta http-equiv="Content-Security-Policy" content="default-src *">' +
        '<style>.x{color:red}</style><script>window.__headRan = true;</script></head>' +
        '<body><p class="x">hi</p><script>window.__bodyRan = true;</script></body></html>',
      nonce: 'n5',
    });
    expect(html).toContain('<p class="x">hi</p>');
    expect(html).toContain('.x{color:red}');
    expect(html).toContain('window.__headRan');
    expect(html).toContain('window.__bodyRan');
    expect(html).not.toContain('<title>evil</title>');
    // The model's permissive policy is gone; ours is the only one.
    expect(html).not.toContain('default-src *');
    expect(html.match(/Content-Security-Policy/g)).toHaveLength(1);
    expect(html.indexOf('Content-Security-Policy')).toBeLessThan(html.indexOf('<p class="x">'));
  });

  it('jsonForScript neutralizes line separators and angle brackets', () => {
    const encoded = jsonForScript({ a: '<x>', b: '\u2028' });
    expect(encoded).toContain('\\u003cx\\u003e');
    expect(encoded).toContain('\\u2028');
  });
});
