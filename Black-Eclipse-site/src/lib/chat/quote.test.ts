import { describe, expect, it } from 'vitest';
import {
  DEFAULT_QUOTE_PROMPT,
  MAX_QUOTE_CHARS,
  boundQuote,
  buildQuoteContext,
  quoteFromSelection,
  quoteSourceLabel,
  turnTextForHarness,
} from './quote';

describe('boundQuote', () => {
  it('trims and keeps short text intact', () => {
    expect(boundQuote('  hello  ')).toEqual({ text: 'hello', truncated: false });
  });

  it('marks an over-long selection as truncated', () => {
    const result = boundQuote('x'.repeat(MAX_QUOTE_CHARS + 10));
    expect(result.truncated).toBe(true);
    expect(result.text.endsWith('…')).toBe(true);
  });
});

describe('quoteFromSelection', () => {
  it('returns null for whitespace-only selections', () => {
    expect(quoteFromSelection('   ', { messageId: 'm1', role: 'assistant' })).toBeNull();
  });

  it('keeps the source and author', () => {
    expect(quoteFromSelection('passage', { messageId: 'm1', role: 'assistant', author: 'Bot' }))
      .toEqual({ text: 'passage', messageId: 'm1', role: 'assistant', author: 'Bot' });
  });
});

describe('quoteSourceLabel', () => {
  it('prefers the author, then the role', () => {
    expect(quoteSourceLabel({ text: '', messageId: 'm', role: 'assistant', author: 'Bot' })).toBe('Bot');
    expect(quoteSourceLabel({ text: '', messageId: 'm', role: 'assistant' })).toBe('Eclipse');
    expect(quoteSourceLabel({ text: '', messageId: 'm', role: 'user' })).toBe('You');
  });
});

describe('turnTextForHarness', () => {
  it('leaves quote-free turns unchanged', () => {
    expect(turnTextForHarness({ content: 'Research NVDA' })).toBe('Research NVDA');
  });

  it('prepends the quoted passage with explicit delimiters', () => {
    const text = turnTextForHarness({
      content: 'What does this mean?',
      quote: { text: 'NVDA is expensive', messageId: 'a1', role: 'assistant' },
    });
    expect(text).toContain('The user quoted this passage');
    expect(text).toContain('"""\nNVDA is expensive\n"""');
    expect(text.endsWith('What does this mean?')).toBe(true);
  });

  it('uses the default prompt when the quote is sent alone', () => {
    const text = turnTextForHarness({
      content: '',
      quote: { text: 'passage', messageId: 'a1', role: 'assistant' },
    });
    expect(text.endsWith(DEFAULT_QUOTE_PROMPT)).toBe(true);
  });
});

describe('buildQuoteContext', () => {
  it('labels the source', () => {
    expect(buildQuoteContext({ text: 'x', messageId: 'm', role: 'user' })).toContain('(You)');
  });
});
