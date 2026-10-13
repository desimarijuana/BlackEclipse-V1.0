import { describe, it, expect } from 'vitest';
import { repairMermaid } from './mermaid-repair';

describe('repairMermaid', () => {
  it('quotes a flowchart label that holds reserved characters (observed producer output)', () => {
    const src =
      'flowchart TD\n    J[7. Conflict detection<br/>eps FY2026 → EXPLAINED (currency/unit)<br/>revenue FY2026 → EXPLAINED]';
    const out = repairMermaid(src);
    // The parenthesised/arrow text is now inside a quoted label.
    expect(out).toMatch(/J\["[^"]*\(currency\/unit\)[^"]*"\]/);
    // Only the label changed; the arrow/statement structure is intact.
    expect(out.startsWith('flowchart TD')).toBe(true);
  });

  it('leaves an already-quoted label untouched', () => {
    const src = 'flowchart TB\n  A["policy &gt; attachment (kept)"] --> B';
    expect(repairMermaid(src)).toBe(src.replace('&gt;', '>'));
  });

  it('joins a sequence Note that wrapped across a line', () => {
    const src = [
      'sequenceDiagram',
      '  participant D as Database',
      '  Note over D: NOT VERIFIED — ports 5432 and 6379 are FREE,',
      '  so no local Postgres/Redis is listening',
    ].join('\n');
    const out = repairMermaid(src);
    expect(out).toContain('FREE, so no local Postgres/Redis is listening');
    // The wrapped fragment is joined, so four source lines become three.
    expect(out.split('\n')).toHaveLength(3);
  });

  it('does not join a real message line that starts lowercase', () => {
    const src = ['sequenceDiagram', '  Note over U: hi', '  u->>api: request'].join('\n');
    expect(repairMermaid(src).split('\n')).toHaveLength(3);
  });

  it('decodes HTML entities once (no double decode)', () => {
    expect(repairMermaid('flowchart LR\n A&amp;gt; B')).toContain('&gt;');
    expect(repairMermaid('flowchart LR\n A[policy &gt; tool]')).toContain('policy > tool');
  });

  it('never throws on empty or non-mermaid input', () => {
    expect(repairMermaid('')).toBe('');
    expect(repairMermaid('just some text')).toBe('just some text');
  });
});
