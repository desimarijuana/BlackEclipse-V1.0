import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

// A real-PDF regression guard. The hand-rolled reader yields NOTHING for a PDF
// whose fonts are CID/Identity-H (the common case for reports and decks), so the
// file was silently skipped and the agent told the user "nothing is attached".
// The pdfjs path fixes that, but it depends on the worker MODULE resolving from
// the installed package — which Next's bundler broke. This pins both facts.

const require_ = createRequire(import.meta.url);

describe('pdf extraction wiring', () => {
  it('resolves the pdfjs worker module (the thing Next broke)', () => {
    const worker = require_.resolve('pdfjs-dist/legacy/build/pdf.worker.mjs');
    expect(worker).toMatch(/pdf\.worker\.mjs$/);
    expect(readFileSync(worker).length).toBeGreaterThan(1000);
  });

  it('resolves the pdfjs main module', () => {
    expect(require_.resolve('pdfjs-dist/legacy/build/pdf.mjs')).toMatch(/pdf\.mjs$/);
  });

  it('externalises pdfjs from the Next server bundle', () => {
    const cfg = readFileSync('next.config.ts', 'utf8');
    expect(cfg).toContain('pdfjs-dist');
  });

  it('uses the async pdfjs extractor in the context loader', () => {
    const src = readFileSync('src/lib/chat/session-store.ts', 'utf8');
    expect(src).toContain('extractDocumentText');
  });
});
