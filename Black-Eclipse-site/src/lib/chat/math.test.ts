import { describe, expect, it } from 'vitest';
import { collectLinks, inlineText, parseInline, parseMarkdown } from './markdown';

describe('formulas in the chat Markdown', () => {
  it('reads an inline formula as a math node', () => {
    expect(parseInline('the Sharpe ratio is $S = \\frac{r_p - r_f}{\\sigma}$ here')).toEqual([
      { type: 'text', value: 'the Sharpe ratio is ' },
      { type: 'math', value: 'S = \\frac{r_p - r_f}{\\sigma}', display: false },
      { type: 'text', value: ' here' },
    ]);
  });

  it('reads a single symbol as a formula', () => {
    expect(parseInline('let $r$ be the risk-free rate')).toEqual([
      { type: 'text', value: 'let ' },
      { type: 'math', value: 'r', display: false },
      { type: 'text', value: ' be the risk-free rate' },
    ]);
  });

  it('reads a display formula as a block', () => {
    const blocks = parseMarkdown('$$\\sigma_p^2 = w^2\\sigma^2 + (1-w)^2\\sigma^2$$');
    expect(blocks).toEqual([{ type: 'math', value: '\\sigma_p^2 = w^2\\sigma^2 + (1-w)^2\\sigma^2' }]);
  });

  it('reads a display formula spread over several lines', () => {
    const blocks = parseMarkdown('$$\n\\frac{a}{b}\n$$');
    expect(blocks).toEqual([{ type: 'math', value: '\\frac{a}{b}' }]);
  });

  it('opens a display block directly after a prose line, with no blank line', () => {
    const blocks = parseMarkdown('**Return definition**\n$$r_t = \\frac{P_t}{P_{t-1}} - 1$$');
    expect(blocks).toEqual([
      { type: 'paragraph', children: [{ type: 'strong', children: [{ type: 'text', value: 'Return definition' }] }] },
      { type: 'math', value: 'r_t = \\frac{P_t}{P_{t-1}} - 1' },
    ]);
  });

  it('reads a display formula written in the middle of a line', () => {
    expect(parseInline('The identity $$E = mc^2$$ holds')).toEqual([
      { type: 'text', value: 'The identity ' },
      { type: 'math', value: 'E = mc^2', display: true },
      { type: 'text', value: ' holds' },
    ]);
  });

  it('reads the alternate LaTeX delimiters', () => {
    expect(parseInline('so \\(E = mc^2\\) holds')).toEqual([
      { type: 'text', value: 'so ' },
      { type: 'math', value: 'E = mc^2', display: false },
      { type: 'text', value: ' holds' },
    ]);
    expect(parseMarkdown('\\[a^2 + b^2 = c^2\\]')).toEqual([
      { type: 'math', value: 'a^2 + b^2 = c^2' },
    ]);
  });

  it('tolerates spaces around an inline formula', () => {
    expect(parseInline('where $ x^2 $ applies')).toEqual([
      { type: 'text', value: 'where ' },
      { type: 'math', value: 'x^2', display: false },
      { type: 'text', value: ' applies' },
    ]);
  });

  it('reads a compact term that mixes digits and letters as a formula', () => {
    expect(parseInline('a ratio of $2x$ returns')).toEqual([
      { type: 'text', value: 'a ratio of ' },
      { type: 'math', value: '2x', display: false },
      { type: 'text', value: ' returns' },
    ]);
  });

  it('does not swallow the rest of an in-progress display formula', () => {
    expect(parseMarkdown('text\n$$x^2')).toEqual([
      { type: 'paragraph', children: [{ type: 'text', value: 'text\n$$x^2' }] },
    ]);
  });

  it('treats an escaped dollar as money', () => {
    expect(parseInline('it costs \\$100 today')).toEqual([
      { type: 'text', value: 'it costs $100 today' },
    ]);
  });

  it('keeps money out of the formula', () => {
    expect(parseInline('it trades at $100 today')).toEqual([
      { type: 'text', value: 'it trades at $100 today' },
    ]);
    expect(parseInline('the fee is $1.2bn')).toEqual([{ type: 'text', value: 'the fee is $1.2bn' }]);
    expect(parseInline('US$100 and A$200')).toEqual([{ type: 'text', value: 'US$100 and A$200' }]);
    expect(parseInline('it rose from $5 to $10')).toEqual([
      { type: 'text', value: 'it rose from $5 to $10' },
    ]);
  });

  it('leaves an unpaired dollar sign alone', () => {
    expect(parseInline('the cost is $5 and no closing sign')).toEqual([
      { type: 'text', value: 'the cost is $5 and no closing sign' },
    ]);
  });

  it('keeps a formula inside bold and links', () => {
    expect(parseInline('**$x^2$**')).toEqual([
      { type: 'strong', children: [{ type: 'math', value: 'x^2', display: false }] },
    ]);
    const nodes = parseInline('[$E=mc^2$](https://example.com)');
    expect(nodes[0]).toMatchObject({ type: 'link', href: 'https://example.com' });
  });

  it('carries the formula source into plain text', () => {
    expect(inlineText(parseInline('is $x^2$ ok'))).toBe('is x^2 ok');
  });

  it('does not walk into a formula when collecting links', () => {
    expect(collectLinks(parseInline('[$x^2$](https://example.com)'))).toEqual([
      { href: 'https://example.com', label: 'x^2' },
    ]);
  });
});
