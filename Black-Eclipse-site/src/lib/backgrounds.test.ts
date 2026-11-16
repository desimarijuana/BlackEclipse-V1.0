import { describe, expect, it } from 'vitest';
import {
  CUSTOM_BACKGROUND_ID,
  DEFAULT_BACKGROUND,
  isBackgroundCustomized,
  isVectorImage,
  isWordmarkVisible,
  migrateLegacyLandingColor,
  normalizeBackgroundPrefs,
  normalizePresetBackground,
  resolveBackgroundCss,
  resolveChatBubbleCss,
  resolveChatSurfaceCss,
  shippedBackground,
} from './backgrounds';

describe('chat surface', () => {
  it('is ON by default with a dark/light pair', () => {
    const prefs = normalizeBackgroundPrefs(null);
    expect(prefs.chatSurfaceEnabled).toBe(true);
    expect(prefs.chatSurfaceFill).toBe('flat');
    expect(resolveChatSurfaceCss(prefs)).toEqual({ dark: '#0a0b0b', light: '#f4f4f5', opacity: 1 });
  });

  it('is null when disabled', () => {
    expect(resolveChatSurfaceCss({ ...DEFAULT_BACKGROUND, chatSurfaceEnabled: false })).toBeNull();
  });

  it('resolves flat fills, defaulting an empty color to the theme card', () => {
    const css = resolveChatSurfaceCss({
      ...DEFAULT_BACKGROUND,
      chatSurfaceColor: '',
      chatSurfaceColorLight: '',
    });
    expect(css).toEqual({ dark: 'var(--card)', light: 'var(--card)', opacity: 1 });
  });

  it('resolves a scheme-aware gradient and clamps opacity', () => {
    const css = resolveChatSurfaceCss({
      ...DEFAULT_BACKGROUND,
      chatSurfaceFill: 'gradient',
      chatSurfaceColor: '#101014',
      chatSurfaceColorLight: '#e0e0e0',
      chatSurfaceColor2: '#204020',
      chatSurfaceOpacity: 40,
    });
    expect(css?.dark).toContain('#101014');
    expect(css?.dark).toContain('#204020');
    expect(css?.light).toContain('#e0e0e0');
    expect(css?.opacity).toBeCloseTo(0.4);
  });

  it('normalizes chat-surface fields and unknown fill', () => {
    const prefs = normalizeBackgroundPrefs({
      chatSurfaceEnabled: true,
      chatSurfaceFill: 'plaid',
      chatSurfaceColorLight: '#abcdef',
      chatSurfaceOpacity: 250,
    });
    expect(prefs.chatSurfaceEnabled).toBe(true);
    expect(prefs.chatSurfaceFill).toBe('flat');
    expect(prefs.chatSurfaceColorLight).toBe('#abcdef');
    expect(prefs.chatSurfaceOpacity).toBe(100);
  });
});

describe('chat bubble', () => {
  it('falls back to the shipped fills when no color is set', () => {
    const css = resolveChatBubbleCss({ ...DEFAULT_BACKGROUND, chatBubbleColor: '', chatBubbleColorLight: '' });
    expect(css.light).toContain('color-mix');
    expect(css.dark).toBe('#2e2e2e');
  });

  it('uses the per-scheme picks when set', () => {
    const css = resolveChatBubbleCss({ ...DEFAULT_BACKGROUND, chatBubbleColor: '#111111', chatBubbleColorLight: '#eeeeee' });
    expect(css).toEqual({ light: '#eeeeee', dark: '#111111' });
  });
});

describe('normalizeBackgroundPrefs', () => {
  it('returns shipped defaults for junk input', () => {
    expect(normalizeBackgroundPrefs(null)).toEqual(DEFAULT_BACKGROUND);
    expect(normalizeBackgroundPrefs({ mode: 'plaid', fit: 'stretch' })).toEqual({
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
      mode: 'image', preset: 'eclipse-5', customKey: 'x',
      fit: 'tile', scale: 150, positionX: 20, positionY: 80, dim: 10,
      solidFill: 'pattern', solidColor: '#101010', solidColor2: '#202020',
      solidGradientType: 'radial', solidGradientAngle: 45,
      solidPattern: 'dots', solidPatternOpacity: 33, solidPatternScale: 30,
      textEnabled: true,
      text: 'HELLO', textFont: 'Inter, sans-serif', textColor: '#00ff00',
      textWeight: 800, textLetterSpacing: 0.1, textLineHeight: 1.2, textWidth: 120,
      textItalic: true, textUppercase: true, textScale: 22,
      textOpacity: 40, textPositionY: 30, textAlign: 'left',
      chatSurfaceEnabled: true, chatSurfaceFill: 'gradient',
      chatSurfaceColor: '#111111', chatSurfaceColorLight: '#eeeeee', chatSurfaceColor2: '#222222', chatSurfaceOpacity: 55,
      chatBubbleColor: '#010203', chatBubbleColorLight: '#fdfdfd',
    });
    expect(t).toEqual({
      mode: 'image', preset: 'eclipse-5', customKey: 'x',
      fit: 'tile', scale: 150, positionX: 20, positionY: 80, dim: 10,
      solidFill: 'pattern', solidColor: '#101010', solidColor2: '#202020',
      solidGradientType: 'radial', solidGradientAngle: 45,
      solidPattern: 'dots', solidPatternOpacity: 33, solidPatternScale: 30,
      textEnabled: true,
      text: 'HELLO', textFont: 'Inter, sans-serif', textColor: '#00ff00',
      textWeight: 800, textLetterSpacing: 0.1, textLineHeight: 1.2, textWidth: 120,
      textItalic: true, textUppercase: true, textScale: 22,
      textOpacity: 40, textPositionY: 30, textAlign: 'left',
      chatSurfaceEnabled: true, chatSurfaceFill: 'gradient',
      chatSurfaceColor: '#111111', chatSurfaceColorLight: '#eeeeee', chatSurfaceColor2: '#222222', chatSurfaceOpacity: 55,
      chatBubbleColor: '#010203', chatBubbleColorLight: '#fdfdfd',
    });
  });

  it('rounds wordmark weight to the nearest 100 and clamps the typography', () => {
    expect(normalizeBackgroundPrefs({ textWeight: 750 }).textWeight).toBe(800);
    expect(normalizeBackgroundPrefs({ textWeight: 950 }).textWeight).toBe(900);
    expect(normalizeBackgroundPrefs({ textWidth: 999 }).textWidth).toBe(200);
    expect(normalizeBackgroundPrefs({ textLetterSpacing: -5 }).textLetterSpacing).toBe(-0.1);
    expect(normalizeBackgroundPrefs({ textLineHeight: 5 }).textLineHeight).toBe(2);
    expect(normalizeBackgroundPrefs({ solidGradientAngle: 999 }).solidGradientAngle).toBe(360);
    expect(normalizeBackgroundPrefs({ solidPatternScale: 999 }).solidPatternScale).toBe(80);
    expect(normalizeBackgroundPrefs({ solidPatternScale: 1 }).solidPatternScale).toBe(4);
  });

  it('normalizes the solid fill/pattern and clamps its strength', () => {
    expect(normalizeBackgroundPrefs({ solidFill: 'noise' }).solidFill).toBe(DEFAULT_BACKGROUND.solidFill);
    expect(normalizeBackgroundPrefs({ solidPattern: 'zigzag' }).solidPattern).toBe(DEFAULT_BACKGROUND.solidPattern);
    expect(normalizeBackgroundPrefs({ solidPatternOpacity: 240 }).solidPatternOpacity).toBe(100);
    expect(normalizeBackgroundPrefs({ solidPatternOpacity: -3 }).solidPatternOpacity).toBe(0);
  });

  it('drops the removed pattern mode back to the default mode', () => {
    // The flat/gradient/grid pattern type was removed; a saved 'pattern' pref
    // must resolve to the shipped default mode (solid).
    expect(normalizeBackgroundPrefs({ mode: 'pattern' }).mode).toBe(DEFAULT_BACKGROUND.mode);
    expect(normalizeBackgroundPrefs({ mode: 'pattern', pattern: 'grid' })).toEqual({
      ...DEFAULT_BACKGROUND,
    });
  });

  it('keeps landing text off unless explicitly enabled', () => {
    // Landing text is opt-in: the flag defaults off, even with authored text.
    expect(DEFAULT_BACKGROUND.textEnabled).toBe(false);
    expect(normalizeBackgroundPrefs({ text: 'HELLO' }).textEnabled).toBe(false);
    expect(normalizeBackgroundPrefs({ textEnabled: 'yes' }).textEnabled).toBe(false);
    expect(normalizeBackgroundPrefs({ textEnabled: false }).textEnabled).toBe(false);
    expect(normalizeBackgroundPrefs({ textEnabled: true }).textEnabled).toBe(true);
  });

  it('normalizes and clamps the landing wordmark', () => {
    // Junk falls back to the shipped wordmark defaults.
    const junk = normalizeBackgroundPrefs({ textScale: Number.NaN, textAlign: 'diagonal' });
    expect(junk.text).toBe(DEFAULT_BACKGROUND.text);
    expect(junk.textFont).toBe(DEFAULT_BACKGROUND.textFont);
    expect(junk.textScale).toBe(DEFAULT_BACKGROUND.textScale);
    expect(junk.textAlign).toBe(DEFAULT_BACKGROUND.textAlign);

    // Ranges clamp; an explicitly empty string is honoured (wordmark hidden).
    expect(normalizeBackgroundPrefs({ textScale: 1 }).textScale).toBe(4);
    expect(normalizeBackgroundPrefs({ textScale: 99 }).textScale).toBe(40);
    expect(normalizeBackgroundPrefs({ textOpacity: -5 }).textOpacity).toBe(0);
    expect(normalizeBackgroundPrefs({ textPositionY: 140 }).textPositionY).toBe(100);
    expect(normalizeBackgroundPrefs({ textAlign: 'right' }).textAlign).toBe('right');
    expect(normalizeBackgroundPrefs({ text: '' }).text).toBe('');
    expect(normalizeBackgroundPrefs({ textFont: '' }).textFont).toBe(DEFAULT_BACKGROUND.textFont);
  });

  it('clamps scale to 50–300 and position to 0–100', () => {
    expect(normalizeBackgroundPrefs({ scale: 10 }).scale).toBe(50);
    expect(normalizeBackgroundPrefs({ scale: 999 }).scale).toBe(300);
    expect(normalizeBackgroundPrefs({ scale: 142.6 }).scale).toBe(143);
    expect(normalizeBackgroundPrefs({ positionX: -9 }).positionX).toBe(0);
    expect(normalizeBackgroundPrefs({ positionY: 140 }).positionY).toBe(100);
  });
});

describe('normalizePresetBackground', () => {
  it('keeps only the keys the snapshot supplied (partial merge)', () => {
    const snap = normalizePresetBackground({ text: 'MIDNIGHT', textFont: 'Inter, sans-serif' });
    expect(snap).not.toBeUndefined();
    // The two supplied keys survive; a wallpaper key the preset omitted is NOT
    // invented, so merging over live prefs leaves the user's backdrop alone.
    expect(Object.keys(snap!).sort()).toEqual(['text', 'textFont']);
    expect(snap!.text).toBe('MIDNIGHT');
  });

  it('preserves a full solid-mode snapshot with its wordmark', () => {
    const snap = normalizePresetBackground({
      mode: 'solid', solidFill: 'gradient', solidColor: '#05060f', solidColor2: '#818cf8',
      textEnabled: true, text: 'MIDNIGHT', textColor: '#818cf8', textUppercase: true,
    });
    expect(snap!.mode).toBe('solid');
    expect(snap!.solidFill).toBe('gradient');
    expect(snap!.textEnabled).toBe(true);
    expect(snap!.textUppercase).toBe(true);
  });

  it('normalizes supplied values (clamps, rounds, validates)', () => {
    const snap = normalizePresetBackground({ mode: 'plaid', textScale: 999 });
    // `mode` is supplied but invalid → normalized to the shipped default.
    expect(snap!.mode).toBe(DEFAULT_BACKGROUND.mode);
    expect(snap!.textScale).toBe(40);
  });

  it('returns undefined for junk, empty, or non-object snapshots', () => {
    expect(normalizePresetBackground(null)).toBeUndefined();
    expect(normalizePresetBackground('nope')).toBeUndefined();
    expect(normalizePresetBackground([])).toBeUndefined();
    expect(normalizePresetBackground({})).toBeUndefined();
  });
});

describe('resolveBackgroundCss', () => {
  it('paints a genuine solid fill for mode solid (flat) — no gradient', () => {
    const css = resolveBackgroundCss({ ...DEFAULT_BACKGROUND, mode: 'solid', solidFill: 'flat', solidColor: '#123456' }, null);
    expect(css.url).toBe('none');
    expect(css.color).toBe('#123456');
    expect(css.colorDark).toBe('#123456');
    expect(css.pageImage).toBe('none');
    expect(css.scrim).toBe(false);
    expect(css.suppressPattern).toBe(true);
  });

  it('solid flat with no color follows the theme background, defaulting dark to near-black', () => {
    const css = resolveBackgroundCss({ ...DEFAULT_BACKGROUND, mode: 'solid', solidFill: 'flat', solidColor: '' }, null);
    expect(css.url).toBe('none');
    expect(css.color).toBe('var(--background)');
    expect(css.colorDark).toBe('#0a0b0b');
  });

  it('migrates a retired dark preset landing color to the #0a0b0b default', () => {
    const legacy = { ...DEFAULT_BACKGROUND, mode: 'solid' as const, solidFill: 'flat' as const, solidColor: '#131615' };
    expect(migrateLegacyLandingColor(legacy).solidColor).toBe('');
    expect(resolveBackgroundCss(migrateLegacyLandingColor(legacy), null).colorDark).toBe('#0a0b0b');
  });

  it('keeps an explicit, deliberately-picked landing color', () => {
    const custom = { ...DEFAULT_BACKGROUND, mode: 'solid' as const, solidFill: 'flat' as const, solidColor: '#123456' };
    expect(migrateLegacyLandingColor(custom).solidColor).toBe('#123456');
  });

  it('leaves non-flat and image backdrops untouched', () => {
    expect(migrateLegacyLandingColor({ ...DEFAULT_BACKGROUND, mode: 'solid', solidFill: 'gradient', solidColor: '#131615' }).solidColor).toBe('#131615');
    expect(migrateLegacyLandingColor({ ...DEFAULT_BACKGROUND, mode: 'image', solidColor: '#131615' }).solidColor).toBe('#131615');
  });

  it('solid gradient builds a two-stop wash', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'solid', solidFill: 'gradient', solidColor: '#111', solidColor2: '#222' },
      null,
    );
    expect(css.url).toBe('linear-gradient(160deg, #111 0%, #222 100%)');
  });

  it('solid gradient honors type and angle', () => {
    const linear = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'solid', solidFill: 'gradient', solidColor: '#111', solidColor2: '#222', solidGradientAngle: 45 },
      null,
    );
    expect(linear.url).toBe('linear-gradient(45deg, #111 0%, #222 100%)');
    const radial = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'solid', solidFill: 'gradient', solidColor: '#111', solidColor2: '#222', solidGradientType: 'radial' },
      null,
    );
    expect(radial.url).toBe('radial-gradient(circle at 50% 50%, #222 0%, #111 100%)');
  });

  it('solid gradient end falls back to the brand tint', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'solid', solidFill: 'gradient', solidColor: '', solidColor2: '' },
      null,
    );
    expect(css.url).toContain('rgb(var(--brand-rgb) / 0.55)');
  });

  it('solid pattern layers a texture over the base fill', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'solid', solidFill: 'pattern', solidPattern: 'dots', solidColor: '#000', solidPatternOpacity: 20 },
      null,
    );
    expect(css.url).toContain('radial-gradient');
    expect(css.url).toContain('linear-gradient(#000, #000)');
    expect(css.size).toBe('22px 22px, 100% 100%');
  });

  it('resolves a shipped preset to its encoded public URL', () => {
    const asset = shippedBackground('eclipse-1');
    expect(asset).toBeDefined();
    const css = resolveBackgroundCss({ ...DEFAULT_BACKGROUND, mode: 'image', preset: 'eclipse-1' }, null);
    expect(css.url).toBe(`url("${asset!.url}")`);
    expect(css.url).toContain('eclipse%20bg-1.svg');
    expect(css.pageImage).toBe('none');
    expect(css.scrim).toBe(true);
    expect(css.size).toBe('cover');
  });

  it('resolves the custom preset from the provided data URL', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'image', preset: CUSTOM_BACKGROUND_ID },
      'data:image/png;base64,AAAA',
    );
    expect(css.url).toBe('url("data:image/png;base64,AAAA")');
    expect(css.scrim).toBe(true);
  });

  it('falls back to no image when custom is selected but missing', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'image', preset: CUSTOM_BACKGROUND_ID },
      null,
    );
    expect(css.url).toBe('none');
    expect(css.scrim).toBe(false);
  });

  it('maps fit to size and repeat', () => {
    const base = { ...DEFAULT_BACKGROUND, mode: 'image' as const, preset: 'eclipse-4' };
    expect(resolveBackgroundCss({ ...base, fit: 'contain' }, null).size).toBe('contain');
    const tile = resolveBackgroundCss({ ...base, fit: 'tile' }, null);
    expect(tile.size).toBe('auto');
    expect(tile.repeat).toBe('repeat');
    expect(resolveBackgroundCss({ ...base, fit: 'cover' }, null).repeat).toBe('no-repeat');
  });

  it('maps scale to a clamped zoom multiplier', () => {
    const base = { ...DEFAULT_BACKGROUND, mode: 'image' as const, preset: 'eclipse-1' };
    expect(resolveBackgroundCss({ ...base, scale: 100 }, null).zoom).toBe(1);
    expect(resolveBackgroundCss({ ...base, scale: 200 }, null).zoom).toBe(2);
    expect(resolveBackgroundCss({ ...base, scale: 300 }, null).zoom).toBe(3);
    // Zoom below 100% must shrink the image, not be stuck at 100%.
    expect(resolveBackgroundCss({ ...base, scale: 50 }, null).zoom).toBe(0.5);
    expect(normalizeBackgroundPrefs({ scale: 50 }).scale).toBe(50);
  });

  it('maps position to a focal point', () => {
    const css = resolveBackgroundCss(
      { ...DEFAULT_BACKGROUND, mode: 'image', preset: 'eclipse-1', positionX: 25, positionY: 75 },
      null,
    );
    expect(css.position).toBe('25% 75%');
  });

  it('builds a scrim that is a valid background-image layer', () => {
    const css = resolveBackgroundCss({ ...DEFAULT_BACKGROUND, mode: 'image', dim: 50 }, null);
    expect(css.scrimImage).toBe('linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5))');
  });
});

describe('helpers', () => {
  it('flags non-default backdrops as customized', () => {
    expect(isBackgroundCustomized(DEFAULT_BACKGROUND)).toBe(false);
    expect(isBackgroundCustomized({ ...DEFAULT_BACKGROUND, mode: 'image' })).toBe(true);
  });

  it('shows the wordmark in solid mode, or image mode when opted in', () => {
    const base = { ...DEFAULT_BACKGROUND, text: 'HELLO', textEnabled: false };
    // Image: opt-in only.
    expect(isWordmarkVisible({ ...base, mode: 'image' })).toBe(false);
    expect(isWordmarkVisible({ ...base, mode: 'image', textEnabled: true })).toBe(true);
    // Solid: always (the wordmark IS the backdrop).
    expect(isWordmarkVisible({ ...base, mode: 'solid' })).toBe(true);
    // Empty text never paints.
    expect(isWordmarkVisible({ ...base, mode: 'solid', text: '   ' })).toBe(false);
  });

  it('detects vector images by mime or extension', () => {
    expect(isVectorImage('image/svg+xml', 'x')).toBe(true);
    expect(isVectorImage('', 'logo.SVG')).toBe(true);
    expect(isVectorImage('image/png', 'photo.png')).toBe(false);
  });
});
