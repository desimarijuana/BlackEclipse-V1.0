---
name: black-eclipse-ui
description: Black-Eclipse UI design system — the frosted-glass recipe is the DEFAULT for all cards, panels, tabs, dialogs, and surfaces. Use when building or editing any UI component, card, panel, tab bar, dialog, drawer, tooltip, or styling in this repo. Always prefer the .glass-card / .glass-card-strong / .glass-card-subtle classes over raw backdrop-blur or flat bg-[#0f0f0f] fills.
---

# Black-Eclipse UI — Frosted-Glass Design System

The whole site uses ONE consistent frosted-glass look. When you add or edit any
UI surface, use the shared glass classes below. Do NOT introduce new
`backdrop-blur-*` utilities or flat `bg-[#0f0f0f]/NN` fills for cards/panels.

## The recipe (defined in `src/app/globals.css`)

True frosted glass = translucent tint + strong blur + saturation boost + inset
top/right highlight lines + soft drop shadow. Light mode gets its own override.

```css
.glass-card {
  background: rgba(18, 18, 20, 0.55);
  backdrop-filter: blur(18px) saturate(1.35);
  box-shadow:
    0 8px 30px rgba(0, 0, 0, 0.30),
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    inset -1px 0 0 rgba(255, 255, 255, 0.06);
}
html:not(.dark) .glass-card { /* light-mode override */ }
```

### Hard rules for frosted glass (learned the hard way)

These three requirements are MANDATORY for any frosted-glass surface. If any one
is missing, the frost does not render and it reads as a flat panel:

1. **Declare `backdrop-filter` — and ONLY the standard property.** Do NOT also
   write `-webkit-backdrop-filter`. Next's CSS minifier (lightningcss) collapses
   the pair down to `-webkit-backdrop-filter` alone, and modern Chrome no longer
   supports the `-webkit-` form (`CSS.supports('-webkit-backdrop-filter')` is
   `false`), so the blur silently disappears site-wide. Give lightningcss only
   `backdrop-filter`; it adds any needed prefixes itself.
2. **Keep the tint translucent (alpha ≤ ~0.55 for dark).** `backdrop-filter`
   blurs what is *behind* the element, but an opaque background hides that
   result. A panel at `rgba(18,18,20,0.8)` looks flat even with a 32px blur. If
   you bump opacity to make text readable, you have broken the frost — instead
   raise the blur radius and/or use text shadows.
3. **The element must not sit under a transformed/backdrop-root ancestor.**
   A CSS `transform` or a `filter`/`backdrop-filter` on an ancestor creates a
   containing block + backdrop root, scoping the blur so it can only sample
   within that subtree — producing no visible frost.
   Render floating surfaces (drawers, palettes, popovers) through a
   **`createPortal` to `document.body`** so they sample the real page. This is
   why the workspace widget library / config panel are portaled.
4. **Never use `animation-fill-mode: forwards`/`both` on an ancestor of a
   `backdrop-filter` surface — use `backwards` instead.** A *persisting*
   animation (`forwards`/`both`) keeps the animating element "in effect", which
   makes Chrome treat it as a **backdrop root**. Any descendant `backdrop-filter`
   then samples that empty ancestor instead of the page: `getComputedStyle`
   still reports `blur(32px)`, but the pixels stay perfectly sharp, so the frost
   silently vanishes. This is subtle and was the reason the widget drawer stayed
   flat for so long. Our `.animate-fade-in` / `.animate-fade-in-up` utilities
   therefore use **`backwards`** (holds the start state through any
   `[animation-delay]`, then releases the effect so no backdrop root lingers).
   Corollary: never put `animate-fade-in`/`animate-fade-in-up` (or any
   forwards/both animation) on the *wrapper element that contains* a glass
   drawer/palette — animate a **sibling** (e.g. the dim overlay) instead.
5. **`getComputedStyle(...).backdropFilter` is NOT proof of frost — the pixels
   are.** A surface can report `blur(18px)` and still render perfectly sharp
   (rules 2–4 are the usual causes). When the user says "frosted glass", they
   mean the background must be *visibly blurred*. Always verify with a
   high-contrast test: put a checkerboard behind the surface and compare edge
   energy inside vs. outside it — or simply screenshot and look. If the checker
   still reads sharp through the panel, the frost is broken no matter what the
   computed style says.
6. **Canvas nodes cannot frost.** Graph Studio renders nodes inside React Flow's
   transformed viewport (`.react-flow__viewport` has a `transform`), which is a
   backdrop root: a node's `backdrop-filter` can only sample that subtree, so the
   canvas grid/edges behind it are never blurred and show straight through a
   translucent tint. `.node-card` is therefore intentionally a **near-opaque**
   graphite gradient (alpha ≥ 0.95), not a glass surface — do not "fix" it by
   lowering the alpha or adding `backdrop-blur-*`. The family look comes from the
   inset highlight and soft shadow. The same applies to any HTML overlaid inside
   a transformed/zoomed canvas layer.

### ECharts tooltip overlays (charts, heatmaps, curves)

Tooltips are HTML overlays ECharts injects — they do NOT go through lightningcss,
so their `extraCssText` blur is written verbatim. Three things are mandatory:

```ts
tooltip: {
  backgroundColor: 'rgba(18,18,20,0.5)',   // (a) translucent — NEVER 0.7+
  appendTo: 'body',                          // (b) escape the chart's backdrop root
  borderColor: 'rgba(255,255,255,0.12)',
  borderWidth: 1,
  padding: [10, 12],
  textStyle: { color: '#e5e7eb', fontSize: 11 },
  extraCssText:
    'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; ' +
    'box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
}
```

- (a) A high-alpha fill (e.g. `0.74`, `0.9`, `0.94`) hides the blur — the panel
  reads flat. Keep tooltip tint ≤ ~0.55.
- (b) By default the tooltip is a child of the chart container, which sits inside
  the widget's glass card → a nested backdrop root → the blur samples an empty
  box and does nothing. `appendTo: 'body'` renders the tooltip at `<body>` level
  so it blurs the real page (same lesson as portaling drawers/popovers).
- Never write `-webkit-backdrop-filter` in `extraCssText` (rule 1).

Apply this to every chart tooltip: `eclipse-provider.ts`, `tradingview-chart.tsx`,
`journal/charts`, `journal/trade-replay.tsx`, `economics/panel.tsx`,
`dashboard/chart-widgets.tsx`, `dashboard/heatmap-widget.tsx`,
`portfolio/{fund-manager,use-echart,widgets}.tsx`.


## The tiers — pick by surface

| Class                | Use for                                                          |
| -------------------- | ---------------------------------------------------------------- |
| `.glass-card`        | Standard cards, panels, content blocks (the default)             |
| `.glass-card-strong` | Modals, dialogs, popovers, tooltips, overlays (near-opaque)      |
| `.glass-card-subtle` | Small tiles, table headers, control strips, chips, stat tiles    |
| `.glass-drawer`      | Large side drawers/panels that must read as REAL frost over the dark page — lower opacity + higher blur (widget library, config panel, workspace drawers) |
| `.glass-button`      | Frosted button/toolbar control — translucent tint + blur, no border (workspace toolbar, dashboard header buttons) |
| `.glass-tooltip`     | Hover popups / small floating tips — the EXACT chart-tooltip recipe (tint 0.5, blur 18 + saturate 1.35, radius 14, soft shadow + inset highlight). Use for chart-adjacent hover popups, message-rail previews, "jump to latest" pills — anything that must match the ECharts chart tooltips. MUST be portaled to `<body>` (see hard rule #3); a nested one renders flat. |
| `.tab-bar-subtle`    | Restrained tab strip (control-strip tier) — used via `<TabBar variant="subtle" />` for dense/toolbar-adjacent tab rows |

> Drawers that should show the page through them blurred (e.g. the workspace
> "Add Widget" palette) use **`.glass-drawer`**, not the near-opaque
> `.glass-card-strong` — the strong tier is too opaque for the blur to be
> visible. If a drawer sits above a full-screen dim overlay, keep that overlay
> light (`bg-black/20`) and un-blurred, otherwise it flattens the frost.

## Tabs

Use the `TabBar` component (`src/components/ui/tab-bar.tsx`) for ALL tab bars —
it already applies the frosted `.tab-bar-glass` recipe. Do not hand-roll tab
buttons. It supports icons, badges, a `leading`/`trailing` slot, and a per-item
`active` override for sub-tabs. Pass `variant="subtle"` for the lighter
`.tab-bar-subtle` control-strip tier when the row should read as chrome rather
than a hero card (dense/toolbar-adjacent tabs, e.g. Command Center market tabs).

## Rules

- **Frosted glass ALWAYS has a background blur.** Whenever the user says
  "frosted glass", it MUST include `backdrop-filter: blur(...)` (the glass
  classes already do). Never ship a glass surface as a translucent fill alone.
- **Never write `-webkit-backdrop-filter`** in `globals.css` or inline styles —
  see hard rule #1 above. Standard `backdrop-filter` only.
- **Never raise a glass surface's background alpha above ~0.55** to "improve
  readability" — that hides the blur. See hard rule #2.
- **Portal floating surfaces to `document.body`** if they are nested under a
  transformed/animated ancestor. See hard rule #3.
- **Never use `animation-fill-mode: forwards`/`both` above a glass surface**
  (including on the drawer's own wrapper) — it creates a backdrop root that
  silently kills the blur. Use `backwards`, or animate a sibling. See hard rule #4.
- **Default to `.glass-card`** for any new card/panel. Use `-strong` for
  floating/overlay surfaces, `-subtle` for small tiles/chips, and `.glass-button`
  for toolbar buttons.
- **Hover popups / small tips use `.glass-tooltip`** — it is the exact recipe the
  chart tooltips use, so a popup beside a chart or over the transcript frosts
  identically. `-strong` is the WRONG tier for a tooltip: its 0.85 tint is
  near-opaque and reads flat.
- **`.glass-card-strong` is for large opaque overlays (modals/dialogs), not
  popovers or tooltips.** Its tint (`rgba(16,16,18,0.85)`) is above the ≤0.55
  frosted threshold, so its blur is invisible — it looks like a solid panel.
- Keep Tailwind `border`, `rounded-*`, `shadow-*` utilities as-is; only swap the
  background+blur for the glass class.
- **Do NOT** combine a glass class with `backdrop-blur-*` (double blur).
- **Leave as-is (intentional, not cards):** full-screen dimming overlays
  (dialog/sheet/global-loader backdrops), near-opaque sticky table headers
  (`/95`), colored sentiment gradient cards (keep their own gradient + blur),
  and form inputs/selects (`bg-background/60`, `/80`).
- Keep the light-mode (`html:not(.dark)`) override whenever you add a new glass
  class.
