import { describe, expect, it } from 'vitest';
import { decodeResponseFenceStreaming, finalizeBlockCached, scanCompleteBlocks } from './stream-blocks';

describe('scanCompleteBlocks', () => {
  it('reports not-started when there is no blocks array yet', () => {
    expect(scanCompleteBlocks('{"titl')).toEqual({ started: false, open: false, blocks: [] });
  });

  it('returns only the fully-closed block while a later block is still open', () => {
    const source = '{"blocks":[{"type":"markdown","markdown":"a"},{"type":"metric';
    const scanned = scanCompleteBlocks(source);
    expect(scanned.started).toBe(true);
    expect(scanned.open).toBe(true);
    expect(scanned.blocks).toEqual([{ type: 'markdown', markdown: 'a' }]);
  });

  it('never returns a half-written first block', () => {
    const scanned = scanCompleteBlocks('{"blocks":[{"type":"mark');
    expect(scanned.started).toBe(true);
    expect(scanned.open).toBe(true);
    expect(scanned.blocks).toEqual([]);
  });

  it('closes and extracts the title and every block from a complete envelope', () => {
    const source = '{"title":"Risks","blocks":[{"type":"markdown","markdown":"a"},{"type":"callout","tone":"info","markdown":"b"}]}';
    const scanned = scanCompleteBlocks(source);
    expect(scanned.open).toBe(false);
    expect(scanned.title).toBe('Risks');
    expect(scanned.blocks).toHaveLength(2);
  });

  it('does not close on a brace inside a string', () => {
    const source = '{"blocks":[{"type":"markdown","markdown":"a } b"}]}';
    const scanned = scanCompleteBlocks(source);
    expect(scanned.blocks).toEqual([{ type: 'markdown', markdown: 'a } b' }]);
    expect(scanned.open).toBe(false);
  });

  it('handles an escaped quote inside a string', () => {
    const source = '{"blocks":[{"type":"markdown","markdown":"say \\"hi\\""}]}';
    expect(scanCompleteBlocks(source).blocks).toEqual([{ type: 'markdown', markdown: 'say "hi"' }]);
  });
});

describe('decodeResponseFenceStreaming', () => {
  it('returns empty for blank source', () => {
    expect(decodeResponseFenceStreaming('   ').kind).toBe('empty');
  });

  it('returns ok for a complete envelope', () => {
    const result = decodeResponseFenceStreaming('{"blocks":[{"type":"markdown","markdown":"a"}]}');
    expect(result.kind).toBe('ok');
  });

  it('returns partial with only the closed blocks while streaming', () => {
    const result = decodeResponseFenceStreaming(
      '{"blocks":[{"type":"markdown","markdown":"done"},{"type":"card',
    );
    expect(result.kind).toBe('partial');
    if (result.kind !== 'partial') throw new Error('expected partial');
    expect(result.open).toBe(true);
    expect(result.response.blocks).toHaveLength(1);
    // The open block is never rendered as data.
    expect(result.response.blocks[0].type).toBe('markdown');
  });

  it('returns composing when nothing has closed yet', () => {
    expect(decodeResponseFenceStreaming('{"blocks":[{"type":"mark').kind).toBe('composing');
  });
});

describe('finalizeBlockCached', () => {
  it('returns the same object for the same raw block (memoized)', () => {
    const raw = { type: 'markdown', markdown: 'cache me' };
    expect(finalizeBlockCached(raw)).toBe(finalizeBlockCached(raw));
  });
});
