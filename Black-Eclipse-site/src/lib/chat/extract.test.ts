import { describe, expect, it } from 'vitest';
import { extractText, extensionOf, isTextExtractable } from './extract';
import { SESSION_LIMITS } from './session-types';

const bytes = (s: string) => new Uint8Array(Buffer.from(s, 'utf8'));

describe('extensionOf / isTextExtractable', () => {
  it('reads the extension case-insensitively', () => {
    expect(extensionOf('Notes.MD')).toBe('md');
    expect(extensionOf('archive.tar.gz')).toBe('gz');
    expect(extensionOf('noext')).toBe('');
  });

  it('recognises documents, code and office types', () => {
    expect(isTextExtractable('a.md')).toBe(true);
    expect(isTextExtractable('a.pdf')).toBe(true);
    expect(isTextExtractable('a.docx')).toBe(true);
    expect(isTextExtractable('a.odt')).toBe(true);
    expect(isTextExtractable('a.py')).toBe(true);
    expect(isTextExtractable('a.ts')).toBe(true);
    // An unknown extension is still TRIED (sniffed), so it is "extractable".
    expect(isTextExtractable('a.unknown')).toBe(true);
    // A known binary container is honestly not text-extractable.
    expect(isTextExtractable('a.png')).toBe(false);
    expect(isTextExtractable('a.zip')).toBe(false);
  });
});

describe('extractText', () => {
  it('returns markdown/json/csv text unchanged', () => {
    expect(extractText('a.md', bytes('# Title')).text).toBe('# Title');
    expect(extractText('a.json', bytes('{"a":1}')).text).toBe('{"a":1}');
    expect(extractText('a.csv', bytes('a,b\n1,2')).text).toBe('a,b\n1,2');
  });

  it('reads source code files', () => {
    expect(extractText('a.py', bytes("print('hi')")).text).toBe("print('hi')");
    expect(extractText('a.ts', bytes('let x: number = 1')).text).toBe('let x: number = 1');
    expect(extractText('a.sql', bytes('SELECT 1')).text).toBe('SELECT 1');
  });

  it('strips html tags and decodes common entities', () => {
    const result = extractText('a.html', bytes('<p>a &amp; b</p><script>x</script>'));
    expect(result.ok).toBe(true);
    expect(result.text).toContain('a & b');
    expect(result.text).not.toContain('script');
  });

  it('strips rtf control words', () => {
    const result = extractText('a.rtf', bytes('{\\rtf1\\ansi Hello World}'));
    expect(result.ok).toBe(true);
    expect(result.text).toContain('Hello World');
  });

  it('reads an unknown/no-extension file when its bytes are text', () => {
    expect(extractText('notes', bytes('plain text here')).text).toBe('plain text here');
    expect(extractText('a.unknown', bytes('just some text')).text).toBe('just some text');
  });

  it('reports a genuinely binary file honestly (not a flat refusal)', () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
    const result = extractText('a.png', png);
    expect(result.ok).toBe(false);
    expect(result.note).toMatch(/readable text|binary/i);
  });

  it('rejects empty content', () => {
    const result = extractText('empty.txt', bytes('   \n  '));
    expect(result.ok).toBe(false);
  });

  it('truncates very long text and says so', () => {
    const result = extractText('big.txt', bytes('x'.repeat(SESSION_LIMITS.maxDocChars + 10_000)));
    expect(result.ok).toBe(true);
    expect(result.text?.length).toBe(SESSION_LIMITS.maxDocChars);
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

  it('extracts text from a docx (zip of xml)', () => {
    const doc = makeZip({
      "word/document.xml":
        '<w:document><w:body><w:p><w:r><w:t>Quarterly report</w:t></w:r></w:p>' +
        '<w:p><w:r><w:t>Revenue up 12%</w:t></w:r></w:p></w:body></w:document>',
    });
    const result = extractText('report.docx', doc);
    expect(result.ok).toBe(true);
    expect(result.text).toContain('Quarterly report');
    expect(result.text).toContain('Revenue up 12%');
  });

  it('extracts shared strings from an xlsx', () => {
    const book = makeZip({
      "xl/sharedStrings.xml": "<sst><si><t>Ticker</t></si><si><t>AAPL</t></si></sst>",
    });
    const result = extractText('book.xlsx', book);
    expect(result.ok).toBe(true);
    expect(result.text).toContain('Ticker');
    expect(result.text).toContain('AAPL');
  });

  it('accepts docx/xlsx as extractable', () => {
    expect(isTextExtractable('a.docx')).toBe(true);
    expect(isTextExtractable('a.xlsx')).toBe(true);
  });
});

// ── Minimal ZIP writer (STORE method) for the office tests ───────────────────
// docx/xlsx are ZIP files; this builds a valid one with no compression so the
// reader under test can be exercised without shipping a binary fixture.

function makeZip(files: Record<string, string>): Uint8Array {
  const chunks: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  for (const [name, content] of Object.entries(files)) {
    const nameBuf = Buffer.from(name, "utf8");
    const data = Buffer.from(content, "utf8");
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(0, 8); // method 0 = store
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    local.writeUInt16LE(0, 28);
    chunks.push(local, nameBuf, data);

    const cd = Buffer.alloc(46);
    cd.writeUInt32LE(0x02014b50, 0);
    cd.writeUInt16LE(20, 4);
    cd.writeUInt16LE(20, 6);
    cd.writeUInt16LE(0, 8);
    cd.writeUInt16LE(0, 10); // method 0
    cd.writeUInt32LE(crc, 16);
    cd.writeUInt32LE(data.length, 20);
    cd.writeUInt32LE(data.length, 24);
    cd.writeUInt16LE(nameBuf.length, 28);
    cd.writeUInt32LE(offset, 42);
    central.push(Buffer.concat([cd, nameBuf]));
    offset += local.length + nameBuf.length + data.length;
  }
  const cdBuf = Buffer.concat(central);
  const localBuf = Buffer.concat(chunks);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(Object.keys(files).length, 8);
  eocd.writeUInt16LE(Object.keys(files).length, 10);
  eocd.writeUInt32LE(cdBuf.length, 12);
  eocd.writeUInt32LE(localBuf.length, 16);
  return Buffer.concat([localBuf, cdBuf, eocd]);
}

function crc32(buf: Buffer): number {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return (~c) >>> 0;
}
