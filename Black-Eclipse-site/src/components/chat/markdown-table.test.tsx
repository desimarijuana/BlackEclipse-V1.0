import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Markdown } from './markdown';

// A table's alignment is per COLUMN, shared by the header and every body cell.
// The old renderer aligned each numeric cell individually, so a mixed column
// flipped sides and the header sat opposite its values.

describe('Markdown table alignment', () => {
  it('right-aligns a numeric column in both the header and the body', () => {
    const out = renderToStaticMarkup(
      <Markdown content={'| Metric | Value |\n| --- | --- |\n| Revenue | 1,234 |\n| Cost | 567 |'} />,
    );
    expect(out).toMatch(/<th[^>]*style="text-align:left"[^>]*>Metric<\/th>/);
    expect(out).toMatch(/<th[^>]*style="text-align:right"[^>]*>Value<\/th>/);
    expect(out).toMatch(/<td[^>]*style="text-align:right"[^>]*>1,234<\/td>/);
  });

  it('keeps every cell of a mixed column on the same side', () => {
    const out = renderToStaticMarkup(
      <Markdown content={'| Note |\n| --- |\n| 1,234 |\n| n/a |'} />,
    );
    // One of two values is numeric (50%) — the whole column stays left.
    expect(out).toMatch(/<td[^>]*style="text-align:left"[^>]*>1,234<\/td>/);
    expect(out).not.toContain('text-align:right');
  });

  it('honours an explicit GFM alignment over inference', () => {
    const out = renderToStaticMarkup(
      <Markdown content={'| Value |\n| :--- |\n| 1,234 |'} />,
    );
    expect(out).toMatch(/<th[^>]*style="text-align:left"[^>]*>Value<\/th>/);
    expect(out).toMatch(/<td[^>]*style="text-align:left"[^>]*>1,234<\/td>/);
  });
});
