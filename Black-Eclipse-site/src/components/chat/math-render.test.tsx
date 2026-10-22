import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import katex from 'katex';
import { Markdown } from '@/components/chat/markdown';

describe('a formula in the chat', () => {
  it('shows the formula source while the typesetter loads', () => {
    // A JSX attribute is not a JS string: the backslashes are written inside a
    // JS expression, so `\\frac` reaches the renderer as `\frac`.
    const content = 'the Sharpe ratio is $S = \\frac{r_p - r_f}{\\sigma}$';
    const html = renderToStaticMarkup(<Markdown content={content} />);
    expect(html).toContain('S = \\frac{r_p - r_f}{\\sigma}');
  });

  it('is typeset by KaTeX once it is loaded', () => {
    const html = katex.renderToString('S = \\frac{r_p - r_f}{\\sigma}', { throwOnError: false });
    expect(html).toContain('katex');
    expect(html).toContain('frac');
  });

  it('keeps a formula KaTeX cannot parse visible instead of throwing', () => {
    const html = katex.renderToString('\\frac{', { throwOnError: false });
    expect(html).toContain('katex');
  });

  it('leaves money alone', () => {
    const html = renderToStaticMarkup(<Markdown content="it trades at $100 and rose to $120" />);
    expect(html).toContain('$100');
    expect(html).not.toContain('katex');
  });

  it('does not leave the display delimiters around a formula that follows prose', () => {
    // The model writes `**Return definition**\n$$r_t = ...$$` with no blank
    // line. The block must start at the formula, so no literal `$` survives.
    const content = '**Return definition**\n$$r_t = \\frac{P_t}{P_{t-1}} - 1$$';
    const html = renderToStaticMarkup(<Markdown content={content} />);
    expect(html).toContain('r_t = \\frac{P_t}{P_{t-1}} - 1');
    expect(html).not.toContain('$$');
  });
});
