import { describe, expect, it } from 'vitest';
import {
  CUSTOM_BACKGROUND_ID,
  DEFAULT_BACKGROUND,
  isBackgroundCustomized,
  isVectorImage,
  normalizeBackgroundPrefs,
  resolveBackgroundCss,
  shippedBackground,
} from './backgrounds';

describe('normalizeBackgroundPrefs', () => {
  it('returns shipped defaults for junk input', () => {
    expect(normalizeBackgroundPrefs(null)).toEqual(DEFAULT_BACKGROUND);
    expect(normalizeBackgroundPrefs({ mode: 'plaid', pattern: 'no', fit: 'stretch' })).toEqual({
      ...DEFAULT_BACKGROUND,
      preset: DEFAULT_BACKGROUND.preset,
    });
  });

  it('clamps dim into 0–100 and rounds it', () => {
    expect(normalizeBackgroundPrefs({ dim: 240 }).dim).toBe(100);
    expect(normalizeBackgroundPrefs({ dim: -4 }).dim).toBe(0);
    expect(normalizeBackgroundPrefs({ dim: 42.6 }).dim).toBe(43);
    expect(normalizeBackgroundPrefs({ dim: Number.NaN }).dim).toBe(DEFAULT_BACKGROUND.dim);
  });

  it('accepts every valid enum value', () => {
    const t = normalizeBackgroundPrefs({
      mode: 'image', pattern: 'grid', preset: 'eclipse-5', customKey: 'x',
      fit: 'tile', scale: 150, positionX: 20, positionY: 80, dim: 10,
    });
    expect(t).toEqual({
      mode: 'image', pattern: 'grid', preset: 'eclipse-5', customKey: 'x',
      fit: 'tile', scale: 150, positionX: 20, positionY: 80, dim: 10,
    });
  });

  it('clamps scale to 50–300 and position to 0–100', () => {
    expect(normalizeBackgroundPrefs({ scale: 10 }).scale).toBe(50);
    expect(normalizeBackgroundPrefs({ scale: 999 }).scale).toBe(300);
    expect(normalizeBackgroundPrefs({ scale: 142.6 }).scale).toBe(143);
    expect(normalizeBackgroundPrefs({ positionX: -9 }).positionX).toBe(0);
    expect(normalizeBackgroundPrefs({ positionY: 140 }).positionY).toBe(100);
  });
});

describe('resolveBackgroundCss', () => {
  it('is transparent for mode none', () => {
    const css = resolveBackgroundCss({ ...DEFAULT_BACKGROUND, mode: 'none' }, 'none', null);
    expect(css.url).toBe('none');
    expect(css.pageImage).toBe('none');
    expect(css.scrim).toBe(false);
  });

  it('uses the theme pattern for pattern mode (pattern layer only)', () => {
    const gradient = 'radial-gradient(red, transparent)';
    const css = resolveBackgroundCss({ ...DEFAULT_BACKGROUND, mode: 'pattern', pattern: 'gradient' }, gradient, null);
    expect(css.pageImage).toBe(gradient);
    expect(css.url).toBe('none');
    expect(css.scrim).toBe(false);
  });

  it('resolves a shipped preset to its encoded public URL', () => {
    const asset = shippedBackground('eclipse-1');
    expect(asset).toBeDefined();
    const css = resolveBackgroundCss({ ...DEFAULT_BACKGROUND, mode: 'image', preset: 'eclipse-1' }, 'none', null);
    expect(css.url).toBe(`url("${asset!.url}")`);
    expect(css.url).toContain('eclipse%20bg-1.svg');
    expect(css.pageImage).toBe('none');
    expect(css.scrim).toBe(true);
    expect(css.size).toBe('cover');
  });

  it('resolves the custom preset from the provided data URL', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'image', preset: CUSTOM_BACKGROUND_ID },
      'none',
      'data:image/png;base64,AAAA',
    );
    expect(css.url).toBe('url("data:image/png;base64,AAAA")');
    expect(css.scrim).toBe(true);
  });

  it('falls back to no image when custom is selected but missing', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'image', preset: CUSTOM_BACKGROUND_ID },
      'none',
      null,
    );
    expect(css.url).toBe('none');
    expect(css.scrim).toBe(false);
  });

  it('maps fit to size and repeat', () => {
    const base = { ...DEFAULT_BACKGROUND, mode: 'image' as const, preset: 'eclipse-4' };
    expect(resolveBackgroundCss({ ...base, fit: 'contain' }, 'none', null).size).toBe('contain');
    const tile = resolveBackgroundCss({ ...base, fit: 'tile' }, 'none', null);
    expect(tile.size).toBe('auto');
    expect(tile.repeat).toBe('repeat');
    expect(resolveBackgroundCss({ ...base, fit: 'cover' }, 'none', null).repeat).toBe('no-repeat');
  });

  it('maps scale to a clamped zoom multiplier', () => {
    const base = { ...DEFAULT_BACKGROUND, mode: 'image' as const, preset: 'eclipse-1' };
    expect(resolveBackgroundCss({ ...base, scale: 100 }, 'none', null).zoom).toBe(1);
    expect(resolveBackgroundCss({ ...base, scale: 200 }, 'none', null).zoom).toBe(2);
    expect(resolveBackgroundCss({ ...base, scale: 300 }, 'none', null).zoom).toBe(3);
    // Zoom below 100% must shrink the image, not be stuck at 100%.
    expect(resolveBackgroundCss({ ...base, scale: 50 }, 'none', null).zoom).toBe(0.5);
    expect(normalizeBackgroundPrefs({ scale: 50 }).scale).toBe(50);
  });

  it('maps position to a focal point', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'image', preset: 'eclipse-1', positionX: 25, positionY: 75 },
      'none', null,
    );
    expect(css.position).toBe('25% 75%');
  });

  it('builds a scrim that is a valid background-image layer', () => {
    const css = resolveBackgroundCss({ ...DEFAULT_BACKGROUND, mode: 'image', dim: 50 }, 'none', null);
    expect(css.scrimImage).toBe('linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5))');
  });
});

describe('helpers', () => {
  it('flags non-default backdrops as customized', () => {
    expect(isBackgroundCustomized(DEFAULT_BACKGROUND)).toBe(false);
    expect(isBackgroundCustomized({ ...DEFAULT_BACKGROUND, mode: 'none' })).toBe(true);
    expect(isBackgroundCustomized({ ...DEFAULT_BACKGROUND, mode: 'pattern' })).toBe(true);
  });

  it('detects vector images by mime or extension', () => {
    expect(isVectorImage('image/svg+xml', 'x')).toBe(true);
    expect(isVectorImage('', 'logo.SVG')).toBe(true);
    expect(isVectorImage('image/png', 'photo.png')).toBe(false);
  });
});
