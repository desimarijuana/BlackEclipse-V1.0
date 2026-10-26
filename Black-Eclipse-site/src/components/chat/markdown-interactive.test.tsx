import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Markdown } from './markdown';

// The reliability path: a fenced HTML/SVG app must become a live sandboxed
// preview, not a wall of code. The same is true while the model answers with
// prose + a code fence instead of the `interactive` block.
describe('Markdown app fences render live', () => {
  it('renders an ```html fence as a sandboxed iframe', () => {
    const out = renderToStaticMarkup(
      <Markdown content={'```html\n<h1>hi</h1>\n```'} />,
    );
    expect(out).toContain('<iframe');
    expect(out).toContain('sandbox="allow-scripts"');
    expect(out).not.toContain('sandbox="allow-scripts allow-same-origin"');
    expect(out).toContain('Content-Security-Policy');
    expect(out).not.toContain('<pre');
  });

  it('renders an ```svg fence as a live preview', () => {
    const out = renderToStaticMarkup(
      <Markdown content={'```svg\n<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>\n```'} />,
    );
    expect(out).toContain('<iframe');
    expect(out).not.toContain('<pre');
  });

  it('keeps a fence as code while the turn is streaming', () => {
    const out = renderToStaticMarkup(
      <Markdown content={'```html\n<h1>hi</h1>\n```'} streaming />,
    );
    expect(out).not.toContain('<iframe');
    expect(out).toContain('<pre');
    expect(out).toContain('&lt;h1&gt;');
  });

  it('leaves a non-app fence as code', () => {
    const out = renderToStaticMarkup(
      <Markdown content={'```ts\nconst x = 1;\n```'} />,
    );
    expect(out).not.toContain('<iframe');
  });
});
