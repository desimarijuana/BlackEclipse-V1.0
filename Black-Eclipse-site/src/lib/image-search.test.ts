import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const safeGet = vi.fn();
const validateOutboundUrl = vi.fn((url: string) => {
  try {
    const protocol = new URL(url).protocol;
    if (protocol !== 'http:' && protocol !== 'https:') return { safe: false, reason: 'scheme' };
    return { safe: true };
  } catch {
    return { safe: false, reason: 'invalid' };
  }
});

vi.mock('@/lib/connectors/security', () => ({
  safeGet: (...args: unknown[]) => safeGet(...args),
  validateOutboundUrl: (url: string) => validateOutboundUrl(url),
  OutboundError: class OutboundError extends Error {
    code = 'transport_error';
  },
}));

vi.mock('@/lib/provider-keys', () => ({
  resolveProviderKey: vi.fn(async () => null),
}));

import { searchImages, clearImageSearchCache, imageProviderHealth } from '@/lib/image-search';

function res(payload: unknown, status = 200) {
  return { status, text: JSON.stringify(payload), bytes: 10, headers: {} };
}

beforeEach(() => {
  clearImageSearchCache();
  safeGet.mockReset();
  validateOutboundUrl.mockClear();
});
afterEach(() => vi.clearAllMocks());

describe('searchImages — keyless Openverse', () => {
  it('normalizes a direct image URL, thumbnail, dimensions and attribution', async () => {
    safeGet.mockResolvedValue(
      res({
        results: [
          {
            id: 'a',
            title: 'H100 GPU',
            url: 'https://cdn.example.com/h100.jpg',
            thumbnail: 'https://cdn.example.com/h100-thumb.jpg',
            foreign_landing_url: 'https://example.com/h100',
            creator: 'NVIDIA',
            license: 'cc0',
            license_version: '1.0',
            width: 1200,
            height: 800,
            filetype: 'jpg',
          },
        ],
      }),
    );
    const outcome = await searchImages('NVIDIA H100 GPU');
    expect(outcome.provider).toBe('openverse');
    expect(outcome.results).toHaveLength(1);
    const img = outcome.results[0];
    expect(img.imageUrl).toBe('https://cdn.example.com/h100.jpg');
    expect(img.thumbnailUrl).toBe('https://cdn.example.com/h100-thumb.jpg');
    expect(img.sourceUrl).toBe('https://example.com/h100');
    expect(img.sourceDomain).toBe('cdn.example.com');
    expect(img.width).toBe(1200);
    expect(img.height).toBe(800);
    expect(img.attribution).toContain('NVIDIA');
    expect(img.validationStatus).toBe('metadata_ok');
  });

  it('drops a result with no direct image URL (a source page is not an image)', async () => {
    safeGet.mockResolvedValue(res({ results: [{ title: 'no url', foreign_landing_url: 'https://example.com' }] }));
    const outcome = await searchImages('something');
    expect(outcome.results).toHaveLength(0);
    expect(outcome.diagnostics.some((d) => d.category === 'zero_results')).toBe(true);
  });
});

describe('searchImages — safety and dedupe', () => {
  it('never returns a non-http(s) image URL', async () => {
    safeGet.mockResolvedValue(
      res({
        results: [
          { title: 'xss', url: 'javascript:alert(1)', foreign_landing_url: 'https://e.com' },
          { title: 'ok', url: 'https://cdn.example.com/ok.png', foreign_landing_url: 'https://e.com' },
        ],
      }),
    );
    const outcome = await searchImages('x');
    expect(outcome.results).toHaveLength(1);
    expect(outcome.results[0].imageUrl).toBe('https://cdn.example.com/ok.png');
  });

  it('deduplicates identical image URLs', async () => {
    safeGet.mockResolvedValue(
      res({
        results: [
          { title: 'a', url: 'https://cdn.example.com/same.jpg' },
          { title: 'b', url: 'https://cdn.example.com/same.jpg' },
        ],
      }),
    );
    const outcome = await searchImages('dup');
    expect(outcome.results).toHaveLength(1);
  });

  it('coalesces identical in-flight searches', async () => {
    let resolveGet: (v: unknown) => void = () => {};
    safeGet.mockImplementation(
      () =>
        new Promise((r) => {
          resolveGet = r;
        }),
    );
    const p1 = searchImages('coalesce');
    const p2 = searchImages('coalesce');
    await vi.waitFor(() => expect(safeGet).toHaveBeenCalled());
    resolveGet(res({ results: [{ title: 'a', url: 'https://cdn.example.com/a.jpg' }] }));
    const [a, b] = await Promise.all([p1, p2]);
    expect(a.results).toHaveLength(1);
    expect(b).toBe(a);
  });

  it('reports a genuine empty query as invalid', async () => {
    const outcome = await searchImages('   ');
    expect(outcome.results).toHaveLength(0);
    expect(outcome.diagnostics[0].category).toBe('invalid_request');
  });
});

describe('imageProviderHealth', () => {
  it('marks Brave as credential-required and unavailable without a key', async () => {
    const health = await imageProviderHealth();
    const brave = health.find((h) => h.name === 'brave-images');
    expect(brave?.requiresCredentials).toBe(true);
    expect(brave?.available).toBe(false);
    expect(health.find((h) => h.name === 'openverse')?.available).toBe(true);
  });
});
