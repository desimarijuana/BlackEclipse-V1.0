import { describe, it, expect } from 'vitest';
import {
  splitResponseSegments,
  decodeResponseFence,
  parseFirstResponseFence,
  hasResponseFence,
} from './parse';

const ENVELOPE = '```eclipse-response\n{ "schemaVersion": "1.0", "blocks": [ { "type": "markdown", "markdown": "hi" } ] }\n```';

describe('response fence parsing', () => {
  it('splits prose and response segments', () => {
    const segments = splitResponseSegments(`Before\n\n${ENVELOPE}\n\nAfter`);
    expect(segments.map((s) => s.kind)).toEqual(['markdown', 'response', 'markdown']);
  });

  it('marks an unterminated fence as not closed', () => {
    const segments = splitResponseSegments('```eclipse-response\n{ "blocks": [] }');
    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe('response');
    if (segments[0].kind === 'response') expect(segments[0].closed).toBe(false);
  });

  it('decodes a valid fence into a validated response', () => {
    const result = decodeResponseFence('{ "blocks": [ { "type": "markdown", "markdown": "hi" } ] }');
    expect(result.status).toBe('ok');
    if (result.status === 'ok') expect(result.response.blocks[0].type).toBe('markdown');
  });

  it('treats malformed JSON as incomplete while streaming and malformed when settled', () => {
    const body = '{ "blocks": [ { "type": "markdown", "markdown": "hi" }';
    expect(decodeResponseFence(body, false).status).toBe('incomplete');
    expect(decodeResponseFence(body, true).status).toBe('malformed');
  });

  it('reports an empty body', () => {
    expect(decodeResponseFence('   ').status).toBe('empty');
  });

  it('parses the first fence and detects presence', () => {
    expect(hasResponseFence('hello')).toBe(false);
    expect(hasResponseFence(ENVELOPE)).toBe(true);
    const decoded = parseFirstResponseFence(ENVELOPE);
    expect(decoded?.status).toBe('ok');
  });
});
