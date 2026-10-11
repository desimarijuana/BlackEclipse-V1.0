import { describe, it, expect } from 'vitest';
import { markdownToPlainText, responseToJson, tableToCsv, toBase64Utf8 } from './export';
import { parseResponsePayload } from './contract';

describe('export helpers', () => {
  it('serialises a response to stable JSON', () => {
    const response = parseResponsePayload({ blocks: [{ type: 'markdown', markdown: 'hi' }] });
    const json = responseToJson(response);
    expect(JSON.parse(json).blocks[0].markdown).toBe('hi');
  });

  it('escapes commas and quotes in CSV', () => {
    const csv = tableToCsv(
      [{ key: 'a', label: 'Name' }, { key: 'b', label: 'Note' }],
      [{ a: 'Acme, Inc.', b: 'He said "hi"' }, { a: 'Beta', b: 42 }],
    );
    const lines = csv.split('\n');
    expect(lines[0]).toBe('Name,Note');
    expect(lines[1]).toBe('"Acme, Inc.","He said ""hi"""');
    expect(lines[2]).toBe('Beta,42');
  });

  it('flattens markdown, including tables and headings, to plain text', () => {
    const text = markdownToPlainText('# Title\n\nHello **world**.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |');
    expect(text).toContain('TITLE');
    expect(text).toContain('Hello world.');
    expect(text).toContain('a | b');
    expect(text).toContain('1 | 2');
  });

  it('base64-encodes UTF-8 text', () => {
    expect(toBase64Utf8('hello')).toBe('aGVsbG8=');
    // Non-ASCII must not throw.
    expect(() => toBase64Utf8('café — €')).not.toThrow();
  });
});
