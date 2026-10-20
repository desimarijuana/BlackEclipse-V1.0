import { Check } from '@/lib/icons';
import { normalizeHex, type EclipseTheme } from '@/lib/theme';
import { cn } from '@/lib/utils';

/** `#rrggbb` → the `r g b` triplet used by `rgb(... / alpha)` CSS. */
export function rgbTriplet(hex: string): string {
  const n = normalizeHex(hex);
  if (!n) return '18 18 20';
  return [n.slice(1, 3), n.slice(3, 5), n.slice(5, 7)]
    .map((h) => parseInt(h, 16))
    .join(' ');
}

/** A miniature of the app rendered from a theme's own tokens. */
export function ThemePreview({ theme }: { theme: EclipseTheme }) {
  const c = theme.colors;
  const dark = theme.scheme !== 'light';
  const surface = `rgb(${rgbTriplet(c.surface)} / ${theme.glass.enabled ? Math.min(0.85, theme.glass.opacity + 0.25) : 0.97})`;
  return (
    <span
      className="block w-full overflow-hidden rounded-lg border border-white/10"
      style={{ backgroundColor: c.background }}
      aria-hidden
    >
      <span className="flex h-[86px]">
        <span
          className="flex w-[22%] shrink-0 flex-col justify-center gap-1.5 px-1.5"
          style={{ backgroundColor: `rgb(${rgbTriplet(theme.sidebar.tint)} / ${theme.sidebar.opacity})` }}
        >
          <span className="h-1 w-full rounded-full" style={{ backgroundColor: c.primary }} />
          <span className="h-1 w-2/3 rounded-full" style={{ backgroundColor: c.accent, opacity: 0.7 }} />
          <span className="h-1 w-3/4 rounded-full" style={{ backgroundColor: c.text, opacity: 0.25 }} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1.5 p-1.5">
          <span className="flex gap-1.5">
            <span className="h-6 flex-1 rounded border border-white/10" style={{ backgroundColor: surface }} />
            <span className="h-6 flex-1 rounded border border-white/10" style={{ backgroundColor: surface }} />
          </span>
          <span
            className="relative flex flex-1 items-center justify-center overflow-hidden rounded border border-white/10"
            style={{ backgroundColor: surface }}
          >
            <svg viewBox="0 0 100 28" preserveAspectRatio="none" className="h-full w-full">
              <polyline
                points="0,22 18,14 32,18 50,7 68,13 84,4 100,9"
                fill="none"
                stroke={c.primary}
                strokeWidth={2}
              />
            </svg>
          </span>
          <span className="flex gap-1">
            <span className="h-1 flex-1 rounded-full" style={{ backgroundColor: c.text, opacity: 0.18 }} />
            <span className="h-1 w-3 rounded-full" style={{ backgroundColor: c.bullish }} />
            <span className="h-1 w-3 rounded-full" style={{ backgroundColor: c.bearish }} />
          </span>
        </span>
      </span>
      <span className="block h-1.5" style={{ backgroundColor: dark ? c.accent : c.secondary, opacity: 0.5 }} />
    </span>
  );
}

/** A preset tile: preview plus label/description. */
export function PresetTile({
  theme,
  label,
  description,
  active,
  onClick,
}: {
  theme: EclipseTheme;
  label: string;
  description: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={description}
      className={cn(
        'flex flex-col gap-2 rounded-xl border p-2.5 text-left transition-all cursor-pointer',
        active
          ? 'bg-primary/10 border-primary/40 shadow-sm shadow-primary/10'
          : 'border-border/20 glass-card-subtle hover:border-border/40',
      )}
    >
      <ThemePreview theme={theme} />
      <span className="flex flex-col min-w-0 px-0.5">
        <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          {label}
          {active && <Check className="w-3 h-3 text-primary shrink-0" />}
        </span>
        <span className="text-[10px] text-muted-foreground truncate">{description}</span>
      </span>
    </button>
  );
}
