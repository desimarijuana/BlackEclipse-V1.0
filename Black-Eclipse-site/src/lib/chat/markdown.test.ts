import { describe, expect, it } from 'vitest';
import { parseInline, parseMarkdown } from './markdown';

describe('parseMarkdown block parsing', () => {
  it('turns a plain paragraph into a paragraph block', () => {
    expect(parseMarkdown('hello world')).toEqual([
      { type: 'paragraph', children: [{ type: 'text', value: 'hello world' }] },
    ]);
  });

  it('keeps blank lines from merging paragraphs', () => {
    const blocks = parseMarkdown('first\n\nsecond');
    expect(blocks).toHaveLength(2);
    expect(blocks.every((b) => b.type === 'paragraph')).toBe(true);
  });

  it('joins soft-wrapped paragraph lines with a newline', () => {
    const [block] = parseMarkdown('line one\nline two');
    expect(block.type).toBe('paragraph');
    expect(block.type === 'paragraph' && block.children[0]).toEqual({
      type: 'text',
      value: 'line one\nline two',
    });
  });

  it('parses ATX headings at every level', () => {
    const blocks = parseMarkdown('# One\n\n### Three');
    expect(blocks[0]).toMatchObject({ type: 'heading', level: 1 });
    expect(blocks[1]).toMatchObject({ type: 'heading', level: 3 });
  });

  it('parses a fenced code block with a language tag and preserves its body', () => {
    const [block] = parseMarkdown('```ts\nconst x = 1;\n```');
    expect(block).toEqual({ type: 'code', language: 'ts', value: 'const x = 1;' });
  });

  it('renders an unterminated fence as code (streaming input)', () => {
    const [block] = parseMarkdown('```\nstill typing');
    expect(block).toEqual({ type: 'code', language: null, value: 'still typing' });
  });

  it('does not treat markdown inside a fence as blocks', () => {
    const [block] = parseMarkdown('```\n# not a heading\n- not a list\n```');
    expect(block.type).toBe('code');
  });

  it('parses unordered and ordered lists', () => {
    const [ul] = parseMarkdown('- a\n- b');
    expect(ul).toMatchObject({ type: 'list', ordered: false });
    expect(ul.type === 'list' && ul.items).toHaveLength(2);

    const [ol] = parseMarkdown('1. a\n2. b');
    expect(ol).toMatchObject({ type: 'list', ordered: true });
  });

  it('parses blockquotes, including nested markdown', () => {
    const [block] = parseMarkdown('> **quoted**');
    expect(block.type).toBe('blockquote');
    expect(block.type === 'blockquote' && block.children[0].type).toBe('paragraph');
  });

  it('parses horizontal rules', () => {
    expect(parseMarkdown('---')).toEqual([{ type: 'hr' }]);
  });

  it('parses a pipe table with alignment and rows', () => {
    const [table] = parseMarkdown(
      '| Symbol | Price | Change |\n| :--- | ---: | :---: |\n| AAPL | 338 | +1.2% |\n| MSFT | 412 | -0.4% |',
    );
    expect(table.type).toBe('table');
    if (table.type !== 'table') return;
    expect(table.align).toEqual(['left', 'right', 'center']);
    expect(table.header).toHaveLength(3);
    expect(table.rows).toHaveLength(2);
    expect(table.rows[0][0]).toEqual([{ type: 'text', value: 'AAPL' }]);
  });

  it('parses a table without outer pipes and inline formatting in cells', () => {
    const [table] = parseMarkdown('Name | Qty\n--- | ---\n**Gold** | 3');
    expect(table.type).toBe('table');
    if (table.type !== 'table') return;
    expect(table.rows[0][0]).toEqual([
      { type: 'strong', children: [{ type: 'text', value: 'Gold' }] },
    ]);
  });

  it('does not mistake a paragraph with a pipe for a table', () => {
    const blocks = parseMarkdown('a | b');
    expect(blocks[0].type).toBe('paragraph');
  });

  it('honours escaped pipes inside table cells', () => {
    const [table] = parseMarkdown('| A |\n| --- |\n| x \\| y |');
    expect(table.type).toBe('table');
    if (table.type !== 'table') return;
    expect(table.rows[0][0]).toEqual([{ type: 'text', value: 'x | y' }]);
  });
});

describe('parseInline', () => {
  it('parses bold, italic and strikethrough', () => {
    expect(parseInline('**bold**')).toEqual([
      { type: 'strong', children: [{ type: 'text', value: 'bold' }] },
    ]);
    expect(parseInline('*italic*')).toEqual([
      { type: 'em', children: [{ type: 'text', value: 'italic' }] },
    ]);
    expect(parseInline('~~gone~~')).toEqual([
      { type: 'del', children: [{ type: 'text', value: 'gone' }] },
    ]);
  });

  it('parses inline code without interpreting its contents', () => {
    expect(parseInline('`**x**`')).toEqual([{ type: 'code', value: '**x**' }]);
  });

  it('nests emphasis inside a code span boundary correctly', () => {
    expect(parseInline('**a `b` c**')).toEqual([
      {
        type: 'strong',
        children: [
          { type: 'text', value: 'a ' },
          { type: 'code', value: 'b' },
          { type: 'text', value: ' c' },
        ],
      },
    ]);
  });

  it('parses links and discards unsafe whitespace targets', () => {
    expect(parseInline('[site](https://example.com)')).toEqual([
      {
        type: 'link',
        href: 'https://example.com',
        children: [{ type: 'text', value: 'site' }],
      },
    ]);
    // A space in the destination is not a valid link, so it stays literal.
    expect(parseInline('[site](not a url)')).toEqual([
      { type: 'text', value: '[site](not a url)' },
    ]);
  });

  it('leaves an unterminated marker as literal text', () => {
    expect(parseInline('**unclosed')).toEqual([{ type: 'text', value: '**unclosed' }]);
    expect(parseInline('trailing **')).toEqual([{ type: 'text', value: 'trailing **' }]);
  });

  it('honours backslash escapes', () => {
    expect(parseInline('\\*not italic\\*')).toEqual([
      { type: 'text', value: '*not italic*' },
    ]);
  });
});
