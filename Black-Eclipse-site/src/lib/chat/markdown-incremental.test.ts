import { describe, expect, it } from 'vitest';
import {
  parseMarkdown,
  parseMarkdownStream,
  stableBoundary,
  type MarkdownParseCache,
} from './markdown';

// The streaming path parses a growing document in pieces. Its output must be
// indistinguishable from one full parse, or a half-written turn would render
// differently depending on how it happened to arrive.

/** Feed `doc` to the incremental parser one line at a time, like a stream. */
function stream(doc: string) {
  let cache: MarkdownParseCache | null = null;
  let blocks: ReturnType<typeof parseMarkdown> = [];
  const lines = doc.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const partial = lines.slice(0, i + 1).join('\n');
    const parsed = parseMarkdownStream(cache, partial);
    cache = parsed.cache;
    blocks = parsed.blocks;
  }
  return blocks;
}

const CORPUS: Record<string, string> = {
  'plain paragraphs': 'First paragraph line one.\nline two.\n\nSecond paragraph.\n\nThird.',
  'heading then prose': '# Title\n\nSome **bold** and `code`.\n\n## Sub\n\nMore text.',
  'fenced code with blank lines': 'Intro.\n\n```ts\nconst a = 1;\n\nconst b = 2;\n```\n\nAfter.',
  'unterminated fence mid-stream': 'Intro.\n\n```py\nprint(1)\n\nprint(2)',
  'table': 'Before.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\nAfter.',
  'blockquote with a blank line': '> one\n>\n> two\n\nNormal paragraph.',
  'display math': 'Before.\n\n$$\nr_t = \\mu + \\epsilon\n$$\n\nAfter.',
  'list': '- one\n- two\n\n1. first\n2. second\n\nEnd.',
  'nested structures': '## Plan\n\n1. Step one\n   - detail\n2. Step two\n\n```json\n{"blocks": [\n  {"type": "markdown"}\n]}\n```\n\nDone.',
  'hr and headings': 'A\n\n---\n\n# H\n\ntext',
  'crlf lines': 'First.\r\n\r\nSecond.\r\n',
  'trailing blank lines': 'One.\n\nTwo.\n\n\n',
};

describe('parseMarkdownStream', () => {
  for (const [name, doc] of Object.entries(CORPUS)) {
    it(`matches a full parse at every step: ${name}`, () => {
      expect(stream(doc)).toEqual(parseMarkdown(doc));
    });
  }

  it('parses character-by-character (worst case) to the same result', () => {
    const doc = 'A **bold** line.\n\n```ts\ncode\n\nmore\n```\n\n> q\n\n| a | b |\n|---|---|\n| 1 | 2 |\n';
    let cache: MarkdownParseCache | null = null;
    let blocks: ReturnType<typeof parseMarkdown> = [];
    for (let i = 1; i <= doc.length; i += 1) {
      const parsed = parseMarkdownStream(cache, doc.slice(0, i));
      cache = parsed.cache;
      blocks = parsed.blocks;
    }
    expect(blocks).toEqual(parseMarkdown(doc));
  });

  it('keeps completed blocks identical so a memoized block can skip re-render', () => {
    const first = parseMarkdownStream(null, 'Alpha.\n\nBeta.\n\n');
    const second = parseMarkdownStream(first.cache, 'Alpha.\n\nBeta.\n\nGamma.');
    // Every block already behind the stable boundary keeps its identity.
    expect(second.blocks[0]).toBe(first.blocks[0]);
    expect(second.blocks[1]).toBe(first.blocks[1]);
    expect(second.blocks[2]).toEqual(parseMarkdown('Gamma.')[0]);
  });

  it('never re-parses the stable prefix when the document only grows', () => {
    const cache = parseMarkdownStream(null, 'One.\n\nTwo.\n\n').cache;
    expect(cache.cut).toBe('One.\n\nTwo.\n\n'.length);
    expect(cache.blocks).toEqual(parseMarkdown('One.\n\nTwo.\n\n'));
  });
});

describe('stableBoundary', () => {
  it('stops before an unterminated fence', () => {
    const doc = 'Intro.\n\n```ts\nunclosed';
    expect(doc.slice(0, stableBoundary(doc))).toBe('Intro.\n\n');
  });

  it('does not cut inside a blockquote that continues after a blank line', () => {
    const doc = '> one\n\n> two\n';
    expect(stableBoundary(doc)).toBe(0);
  });

  it('does not cut inside display math', () => {
    const doc = 'A\n\n$$\nx = 1\n';
    expect(doc.slice(0, stableBoundary(doc))).toBe('A\n\n');
  });

  it('cuts after a completed table', () => {
    const doc = '| a | b |\n|---|---|\n| 1 | 2 |\n\nnext';
    expect(doc.slice(0, stableBoundary(doc))).toBe('| a | b |\n|---|---|\n| 1 | 2 |\n\n');
  });
});
