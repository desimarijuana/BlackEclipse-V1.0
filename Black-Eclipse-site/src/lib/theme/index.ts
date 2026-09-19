// Eclipse theme — public surface.
export {
  DEFAULT_ECLIPSE_THEME,
  STRUCTURAL_THEME_VARS,
  THEME_PRESETS,
  UI_FONT_OPTIONS,
  HEADING_FONT_OPTIONS,
  MONO_FONT_OPTIONS,
  DENSITY_OPTIONS,
  isValidHex,
  normalizeHex,
  normalizeTheme,
  hexToRgb,
  hexToRgbTriplet,
  mixHex,
  luminance,
  readableOn,
  themeCssVars,
  themeMatchesPreset,
  themePresetId,
  buildFaviconDataUrl,
} from './tokens';
export type {
  EclipseTheme,
  ThemeColors,
  ThemeDensity,
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
