import { describe, expect, it } from 'vitest';
import { splitForSpeech, toSpeakableText } from './text';

describe('toSpeakableText', () => {
  it('drops fenced code but keeps the prose around it', () => {
    const input = 'Revenue grew.\n\n```ts\nconst x = 1;\n```\n\nMargins held.';
    expect(toSpeakableText(input)).toBe('Revenue grew. Margins held.');
  });

  it('drops a structured-response envelope entirely', () => {
    const input = [
      'Here is the breakdown.',
      '',
      '```eclipse-response',
      '{ "version": 1, "blocks": [{ "type": "markdown", "body": "hi" }] }',
      '```',
    ].join('\n');
    expect(toSpeakableText(input)).toBe('Here is the breakdown.');
  });

  it('returns empty when the reply is only code', () => {
    expect(toSpeakableText('```js\nconsole.log(1)\n```')).toBe('');
    expect(toSpeakableText('')).toBe('');
  });

  it('keeps link labels and image alt text, never URLs', () => {
    const input = 'See [the filing](https://sec.gov/a?b=1) and ![revenue chart](https://x/y.png).';
    const spoken = toSpeakableText(input);
    expect(spoken).toContain('the filing');
    expect(spoken).toContain('revenue chart');
    expect(spoken).not.toContain('https://');
  });

  it('reads tables as comma-separated rows instead of pipes', () => {
    const input = '| Quarter | Revenue |\n|---|---|\n| Q1 | 10 |';
    const spoken = toSpeakableText(input);
    expect(spoken).not.toContain('|');
    expect(spoken).toContain('Quarter, Revenue.');
    expect(spoken).toContain('Q1, 10.');
  });

  it('removes headings, list markers, emphasis and inline code', () => {
    const input = '## Summary\n\n- **Total** was `AAPL`\n- _Risks_ remain';
    const spoken = toSpeakableText(input);
    expect(spoken).not.toMatch(/[#*_`]/);
    expect(spoken).toContain('Summary');
    expect(spoken).toContain('Total was AAPL');
  });

  it('decodes common HTML entities and strips tags', () => {
    expect(toSpeakableText('AT&amp;T &nbsp;reports <b>growth</b> now')).toBe('AT&T reports growth now.');
  });

  it('strips citation markers and raw autolinks', () => {
    const spoken = toSpeakableText('Revenue rose [1] per <https://example.com/report>.');
    expect(spoken).not.toContain('https://');
    expect(spoken).not.toContain('[1]');
    expect(spoken).toContain('Revenue rose per');
  });

  it('separates blocks that lack terminal punctuation', () => {
    expect(toSpeakableText('# Revenue\nTotal grew')).toBe('Revenue. Total grew.');
  });
});

describe('splitForSpeech', () => {
  it('returns nothing for empty prose', () => {
    expect(splitForSpeech('')).toEqual([]);
    expect(splitForSpeech('   \n  ')).toEqual([]);
  });

  it('merges short sentences into readable chunks', () => {
    expect(splitForSpeech('One. Two. Three.', 220)).toEqual(['One. Two. Three.']);
  });

  it('splits once the chunk limit would be exceeded', () => {
    const chunks = splitForSpeech('First sentence here. Second sentence here.', 25);
    expect(chunks).toEqual(['First sentence here.', 'Second sentence here.']);
  });

  it('breaks a single long sentence without losing text', () => {
    const long = Array.from({ length: 40 }, (_, i) => `word${i}`).join(' ');
    const chunks = splitForSpeech(long, 60);
    expect(chunks.length).toBeGreaterThan(1);
    for (const chunk of chunks) expect(chunk.length).toBeLessThanOrEqual(60);
    expect(chunks.join(' ')).toBe(long);
  });

  it('floors the limit so a tiny maxChars cannot produce empty loops', () => {
    const chunks = splitForSpeech('A sentence that is definitely longer than ten characters.', 10);
    expect(chunks.length).toBeGreaterThan(0);
  });
});
