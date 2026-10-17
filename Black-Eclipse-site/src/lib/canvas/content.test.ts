import { describe, expect, it } from 'vitest';
import { contentFromMessage, contentFromResponse } from './content';
import { parseResponsePayload } from '@/lib/response/contract';

const ENVELOPE = JSON.stringify({
  schemaVersion: '1.0',
  title: 'Quarterly Review',
  blocks: [
    { type: 'markdown', markdown: 'Body.' },
    { type: 'chart', chartType: 'bar', series: [{ name: 'Revenue', data: [{ x: 'Q1', y: 1 }] }] },
  ],
});

function fenced(json: string): string {
  return `Here is the report.\n\n\`\`\`eclipse-response\n${json}\n\`\`\`\n`;
}

describe('canvas content derivation', () => {
  it('treats plain prose as a markdown document', () => {
    const content = contentFromMessage('## Summary\n\nSome prose.');
    expect(content.kind).toBe('markdown');
    expect(content.editable).toBe(false);
    expect(content.markdown).toContain('Summary');
  });

  it('extracts a lone code fence as a code view', () => {
    const content = contentFromMessage('```ts\nexport const x = 1;\n```');
    expect(content.kind).toBe('code');
    expect(content.code?.language).toBe('ts');
    expect(content.code?.text).toContain('export const x');
  });

  it('parses an eclipse-response fence and marks structured output as a report', () => {
    const content = contentFromMessage(fenced(ENVELOPE));
    expect(content.kind).toBe('report');
    expect(content.title).toBe('Quarterly Review');
    expect(content.response?.blocks.some((b) => b.type === 'chart')).toBe(true);
  });

  it('builds report content directly from a parsed response', () => {
    const content = contentFromResponse(parseResponsePayload(JSON.parse(ENVELOPE)));
    expect(content.kind).toBe('report');
    expect(content.response?.title).toBe('Quarterly Review');
  });
});
