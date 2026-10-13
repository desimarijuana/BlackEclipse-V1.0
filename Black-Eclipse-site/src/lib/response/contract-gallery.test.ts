import { describe, expect, it } from 'vitest';
import { parseResponsePayload } from '@/lib/response/contract';

describe('gallery response block', () => {
  it('validates a gallery with http(s) image URLs', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'gallery',
          title: 'H100 GPUs',
          images: [
            { url: 'https://cdn.example.com/h100.jpg', alt: 'An H100 GPU', sourceUrl: 'https://example.com', width: 1200, height: 800 },
            { url: 'https://cdn.example.com/h100-2.jpg', title: 'H100 SXM' },
          ],
        },
      ],
    });
    expect(parsed.diagnostics).toHaveLength(0);
    const block = parsed.blocks[0];
    expect(block.type).toBe('gallery');
    if (block.type === 'gallery') {
      expect(block.images).toHaveLength(2);
      expect(block.images[0].alt).toBe('An H100 GPU');
    }
  });

  it('accepts field synonyms (imageUrl/altText)', () => {
    const parsed = parseResponsePayload({
      blocks: [{ type: 'gallery', images: [{ imageUrl: 'https://a.com/x.jpg', altText: 'x' }] }],
    });
    const block = parsed.blocks[0];
    expect(block.type).toBe('gallery');
    if (block.type === 'gallery') expect(block.images[0].url).toBe('https://a.com/x.jpg');
  });

  it('degrades a gallery whose image URL is javascript: or data:', () => {
    const parsed = parseResponsePayload({
      blocks: [
        {
          type: 'gallery',
          images: [{ url: 'javascript:alert(1)' }],
        },
      ],
    });
    // The whole block fails schema validation (httpUrl refinement) and is
    // surfaced as a diagnostic `unknown` block — never rendered as an image.
    expect(parsed.blocks[0].type).toBe('unknown');
    expect(parsed.diagnostics.some((d) => d.code === 'BLOCK_INVALID')).toBe(true);
  });

  it('rejects an empty gallery', () => {
    const parsed = parseResponsePayload({ blocks: [{ type: 'gallery', images: [] }] });
    expect(parsed.blocks[0].type).toBe('unknown');
  });
});
