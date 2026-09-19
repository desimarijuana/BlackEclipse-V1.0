// Eclipse theme — public surface.
export {
  DEFAULT_ECLIPSE_THEME,
  BRAND_MARK_SRC,
  BRAND_WORDMARK_SRC,
  BRAND_GENERATOR_BACKGROUND,
  BRAND_GENERATOR_SURFACE,
  STRUCTURAL_THEME_VARS,
  THEME_PRESETS,
  UI_FONT_OPTIONS,
  HEADING_FONT_OPTIONS,
  MONO_FONT_OPTIONS,
  DENSITY_OPTIONS,
  SHADOW_OPTIONS,
  BACKGROUND_OPTIONS,
  GLASS_PRESETS,
  isValidHex,
  normalizeHex,
  normalizeTheme,
  hexToRgb,
  hexToRgbTriplet,
  mixHex,
  luminance,
  readableOn,
  themeCssVars,
  themeFromBrandColor,
  themeMatchesPreset,
  themePresetId,
  pageBackgroundImage,
  buildFaviconDataUrl,
} from './tokens';
export type {
  EclipseTheme,
  ThemeColors,
  ThemeDensity,
  ThemeShadow,
  ThemeBackground,
  ThemeGlass,
  ThemePreset,
  FontOption,
} from './tokens';
export {
  useThemeStore,
  useHydrateTheme,
  applyThemeToDocument,
  THEME_STORAGE_KEY,
} from './store';
export type { ThemeStore } from './store';
export { syncChartPaletteFromTheme } from './bridge';
