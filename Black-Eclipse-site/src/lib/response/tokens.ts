// ── Design tokens for the layout primitives ───────────────────────────────────
// A producer composes layout with TOKENS (spacing / radius / tone), never raw
// CSS. Each token is a CLOSED vocabulary mapped here to existing utility classes,
// so a layout block cannot introduce arbitrary styling — the same safety posture
// as the icon allowlist. Server-safe (no React).

export type SpaceToken = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl';
export type RadiusToken = 'none' | 'sm' | 'md' | 'lg' | 'xl';
export type ToneToken = 'neutral' | 'info' | 'success' | 'warning' | 'danger';
export type AlignToken = 'start' | 'center' | 'end' | 'stretch';

export const SPACE_TOKENS: readonly SpaceToken[] = ['none', 'xs', 'sm', 'md', 'lg', 'xl'];
export const RADIUS_TOKENS: readonly RadiusToken[] = ['none', 'sm', 'md', 'lg', 'xl'];
export const TONE_TOKENS: readonly ToneToken[] = ['neutral', 'info', 'success', 'warning', 'danger'];
export const ALIGN_TOKENS: readonly AlignToken[] = ['start', 'center', 'end', 'stretch'];

export const GAP_CLASS: Record<SpaceToken, string> = {
  none: 'gap-0',
  xs: 'gap-1',
  sm: 'gap-2',
  md: 'gap-3',
  lg: 'gap-4',
  xl: 'gap-6',
};

export const PAD_CLASS: Record<SpaceToken, string> = {
  none: 'p-0',
  xs: 'p-1',
  sm: 'p-2',
  md: 'p-3',
  lg: 'p-4',
  xl: 'p-6',
};

export const RADIUS_CLASS: Record<RadiusToken, string> = {
  none: 'rounded-none',
  sm: 'rounded-md',
  md: 'rounded-lg',
  lg: 'rounded-xl',
  xl: 'rounded-2xl',
};

// A tone paints a subtle wash + border; `neutral` is the bare default.
export const TONE_SURFACE: Record<ToneToken, string> = {
  neutral: '',
  info: 'border border-sky-500/25 bg-sky-500/5',
  success: 'border border-emerald-500/25 bg-emerald-500/5',
  warning: 'border border-amber-500/25 bg-amber-500/5',
  danger: 'border border-rose-500/25 bg-rose-500/5',
};

export const ALIGN_CLASS: Record<AlignToken, string> = {
  start: 'items-start',
  center: 'items-center',
  end: 'items-end',
  stretch: 'items-stretch',
};
