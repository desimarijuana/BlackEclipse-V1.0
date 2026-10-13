// ── Inline image gallery rendering (server-rendered) ─────────────────────────
// The `gallery` response block must render ACTUAL <img> elements with src
// pointing at the validated image URL, plus the source-domain attribution link.
// This renders the REAL components, not a mock.

import { describe, it, expect } from 'vitest';
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseResponsePayload } from '@/lib/response/contract';
import { ResponseView } from './response-view';
import { ImageGalleryPanel } from '@/components/chat/image-gallery';

const html = (node: ReactElement): string => renderToStaticMarkup(node);

describe('gallery block rendering', () => {
  it('renders real <img> elements from validated image URLs', () => {
    const response = parseResponsePayload({
      blocks: [
        {
          type: 'gallery',
          title: 'H100 GPUs',
          images: [
            { url: 'https://cdn.example.com/h100.jpg', alt: 'H100 GPU', sourceUrl: 'https://example.com/h100', width: 1200, height: 800 },
          ],
        },
      ],
    });
    const out = html(<ResponseView response={response} />);
    expect(out).toContain('<img');
    expect(out).toContain('https://cdn.example.com/h100.jpg');
    expect(out).toContain('alt="H100 GPU"');
    expect(out).toContain('loading="lazy"');
    expect(out).toContain('example.com'); // source-domain attribution
  });

  it('does not render an image for a rejected (javascript:) URL', () => {
    const response = parseResponsePayload({ blocks: [{ type: 'gallery', images: [{ url: 'javascript:alert(1)' }] }] });
    const out = html(<ResponseView response={response} />);
    expect(out).not.toContain('<img');
  });
});

describe('runtime image gallery panel', () => {
  it('renders actual images from the run blob', () => {
    const out = html(
      <ImageGalleryPanel
        images={{
          type: 'images',
          status: 'collected',
          count: 1,
          results: [{ imageUrl: 'https://cdn.example.com/a.jpg', title: 'A', sourceUrl: 'https://example.com/a', sourceDomain: 'example.com' }],
        }}
      />,
    );
    expect(out).toContain('<img');
    expect(out).toContain('https://cdn.example.com/a.jpg');
  });

  it('renders nothing for an empty/absent blob', () => {
    expect(html(<ImageGalleryPanel images={undefined} />)).toBe('');
    expect(html(<ImageGalleryPanel images={{ results: [] }} />)).toBe('');
  });
});
