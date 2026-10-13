import { describe, expect, it } from 'vitest';
import { coerceGalleryImages, coerceGalleryBlob, coerceGalleryItem } from '@/lib/image-gallery-view';

describe('coerceGalleryItem', () => {
  it('accepts both `url` (response block) and `imageUrl` (run blob)', () => {
    expect(coerceGalleryItem({ url: 'https://a.com/1.jpg' }, 0)?.imageUrl).toBe('https://a.com/1.jpg');
    expect(coerceGalleryItem({ imageUrl: 'https://a.com/2.jpg' }, 1)?.imageUrl).toBe('https://a.com/2.jpg');
  });

  it('rejects javascript: and data: image URLs', () => {
    expect(coerceGalleryItem({ url: 'javascript:alert(1)' }, 0)).toBeNull();
    expect(coerceGalleryItem({ url: 'data:image/png;base64,AAAA' }, 0)).toBeNull();
  });

  it('rejects a candidate with no URL', () => {
    expect(coerceGalleryItem({ title: 'x' }, 0)).toBeNull();
    expect(coerceGalleryItem('https://a.com/x.jpg', 0)).toBeNull();
  });

  it('derives a source domain from the source URL and defaults alt to title', () => {
    const item = coerceGalleryItem({ imageUrl: 'https://cdn.a.com/x.jpg', sourceUrl: 'https://www.source.com/p', title: 'A photo' }, 0);
    expect(item?.sourceDomain).toBe('source.com');
    expect(item?.alt).toBe('A photo');
  });
});

describe('coerceGalleryImages', () => {
  it('deduplicates by image URL and ignores non-arrays', () => {
    const items = coerceGalleryImages([
      { url: 'https://a.com/x.jpg' },
      { url: 'https://a.com/x.jpg' },
      { url: 'https://a.com/y.jpg' },
    ]);
    expect(items).toHaveLength(2);
    expect(coerceGalleryImages(null)).toEqual([]);
  });
});

describe('coerceGalleryBlob', () => {
  it('reads the run blob shape (`results` + `failures`)', () => {
    const view = coerceGalleryBlob({
      type: 'images',
      status: 'collected',
      count: 1,
      results: [{ imageUrl: 'https://a.com/x.jpg', title: 'X' }],
      failures: [{ reason: 'no safe direct image URL' }],
    });
    expect(view.items).toHaveLength(1);
    expect(view.count).toBe(1);
    expect(view.failures).toEqual(['no safe direct image URL']);
  });

  it('returns an empty view for an absent blob', () => {
    expect(coerceGalleryBlob(undefined)).toEqual({ items: [], count: 0, failures: [] });
  });
});
