import { cn } from "@/lib/utils";

// ── Shared header primitives ───────────────────────────────────────────────
// The single source of truth for "icon tile next to a title". Every surface in
// the app — full-screen pages, Settings sections, in-page panels — renders its
// title icon through IconBadge, so the frosted square, the border and the icon
// colour cannot drift apart again.
//
// `border-foreground/10` + `bg-foreground/[0.06]` reads as a quiet neutral on
// both the dark glass and the light frost; a pure `white/10` / `white/[0.06]`
// tile disappears on the light theme.

const ICON_TILE_SIZES = {
  sm: { box: "h-11 w-11 rounded-2xl", icon: 22, title: "text-lg font-semibold" },
  md: { box: "h-12 w-12 rounded-2xl", icon: 26, title: "text-xl md:text-2xl font-semibold" },
  lg: { box: "h-14 w-14 rounded-2xl", icon: 30, title: "text-2xl md:text-4xl font-medium" },
} as const;

export type IconTileSize = keyof typeof ICON_TILE_SIZES;

/** The one and only icon tile. */
export function IconBadge({
  icon: Icon,
  size = "sm",
  iconClassName,
}: {
  icon: React.ElementType;
  size?: IconTileSize;
  /** Extra classes for the glyph itself (e.g. `animate-spin-slow`). */
  iconClassName?: string;
}) {
  const s = ICON_TILE_SIZES[size];
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex shrink-0 items-center justify-center border border-foreground/10 bg-foreground/[0.06]",
        s.box,
      )}
    >
      <Icon className={cn("text-primary", iconClassName)} size={s.icon} />
    </span>
  );
}


/**
 * Full-screen page header: icon tile + serif `<h1>` + optional description and
 * a right-aligned action slot. Shares `IconBadge` with `SectionHeader`, so a
 * page title and a Settings section title are the same visual family.
 */
export function PageHeader({
  icon,
  title,
  description,
  actions,
  size = "md",
  iconClassName,
  className,
}: {
  icon: React.ElementType;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  size?: IconTileSize;
  iconClassName?: string;
  className?: string;
}) {
  const s = ICON_TILE_SIZES[size];
  return (
    <header
      className={cn(
        "mb-5 flex flex-wrap items-center gap-3 border-b border-border/10 pb-4",
        className,
      )}
    >
      <IconBadge icon={icon} size={size} iconClassName={iconClassName} />
      <div className="min-w-0">
        <h1 className={cn("font-serif tracking-tight text-foreground", s.title)}>
          {title}
        </h1>
        {description && (
          <div className="text-xs text-muted-foreground mt-0.5">{description}</div>
        )}
      </div>
      {actions && (
        <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>
      )}
    </header>
  );
}
