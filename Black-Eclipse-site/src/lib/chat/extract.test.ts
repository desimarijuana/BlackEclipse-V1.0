import { describe, expect, it } from 'vitest';
import { extractText, extensionOf, isTextExtractable } from './extract';

const bytes = (s: string) => new Uint8Array(Buffer.from(s, 'utf8'));

describe('extensionOf / isTextExtractable', () => {
  it('reads the extension case-insensitively', () => {
    expect(extensionOf('Notes.MD')).toBe('md');
    expect(extensionOf('archive.tar.gz')).toBe('gz');
    expect(extensionOf('noext')).toBe('');
  });

  it('recognises text and pdf types only', () => {
    expect(isTextExtractable('a.md')).toBe(true);
    expect(isTextExtractable('a.pdf')).toBe(true);
    expect(isTextExtractable('a.png')).toBe(false);
    expect(isTextExtractable('a.exe')).toBe(false);
  });
});

describe('extractText', () => {
  it('returns markdown/json/csv text unchanged', () => {
    expect(extractText('a.md', bytes('# Title')).text).toBe('# Title');
    expect(extractText('a.json', bytes('{"a":1}')).text).toBe('{"a":1}');
    expect(extractText('a.csv', bytes('a,b\n1,2')).text).toBe('a,b\n1,2');
  });

  it('strips html tags and decodes common entities', () => {
    const result = extractText('a.html', bytes('<p>a &amp; b</p><script>x</script>'));
    expect(result.ok).toBe(true);
    expect(result.text).toContain('a & b');
    expect(result.text).not.toContain('script');
  });

  it('rejects an unsupported binary type', () => {
    const result = extractText('a.png', new Uint8Array([0x89, 0x50, 0x4e, 0x47]));
    expect(result.ok).toBe(false);
    expect(result.note).toContain('Unsupported');
  });

  it('rejects empty content', () => {
    const result = extractText('empty.txt', bytes('   \n  '));
    expect(result.ok).toBe(false);
  });

  it('truncates very long text and says so', () => {
    const result = extractText('big.txt', bytes('x'.repeat(30_000)));
    expect(result.ok).toBe(true);
    expect(result.text?.length).toBe(20_000);
    expect(result.note).toContain('Truncated');
  });

  it('extracts text from a minimal uncompressed PDF', () => {
    const pdf = '%PDF-1.4\n4 0 obj << /Length 44 >> stream\nBT /F1 12 Tf (Hello World) Tj ET\nendstream\nendobj';
    const result = extractText('doc.pdf', bytes(pdf));
    expect(result.ok).toBe(true);
    expect(result.text).toContain('Hello World');
  });

  it('drops a UTF-8 BOM', () => {
    const result = extractText('bom.txt', new Uint8Array([0xef, 0xbb, 0xbf, 0x68, 0x69]));
    expect(result.text).toBe('hi');
  });
});
