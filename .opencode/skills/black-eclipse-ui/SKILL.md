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
  -webkit-backdrop-filter: blur(18px) saturate(1.35);
  box-shadow:
    0 8px 30px rgba(0, 0, 0, 0.30),
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    inset -1px 0 0 rgba(255, 255, 255, 0.06);
}
html:not(.dark) .glass-card { /* light-mode override */ }
```

## The three tiers — pick by surface

| Class                | Use for                                                          |
| -------------------- | ---------------------------------------------------------------- |
| `.glass-card`        | Standard cards, panels, content blocks (the default)             |
| `.glass-card-strong` | Modals, dialogs, drawers, popovers, tooltips, sidebar, overlays  |
| `.glass-card-subtle` | Small tiles, table headers, control strips, chips, stat tiles    |

## Tabs

Use the `TabBar` component (`src/components/ui/tab-bar.tsx`) for ALL tab bars —
it already applies the frosted `.tab-bar-glass` recipe. Do not hand-roll tab
buttons. It supports icons, badges, a `leading`/`trailing` slot, and a per-item
`active` override for sub-tabs.

## Rules

- **Default to `.glass-card`** for any new card/panel. Use `-strong` for
  floating/overlay surfaces and `-subtle` for small tiles/chips.
- Keep Tailwind `border`, `rounded-*`, `shadow-*` utilities as-is; only swap the
  background+blur for the glass class.
- **Do NOT** combine a glass class with `backdrop-blur-*` (double blur).
- **Leave as-is (intentional, not cards):** full-screen dimming overlays
  (dialog/sheet/global-loader backdrops), near-opaque sticky table headers
  (`/95`), colored sentiment gradient cards (keep their own gradient + blur),
  and form inputs/selects (`bg-background/60`, `/80`).
- Keep the light-mode (`html:not(.dark)`) override whenever you add a new glass
  class.
