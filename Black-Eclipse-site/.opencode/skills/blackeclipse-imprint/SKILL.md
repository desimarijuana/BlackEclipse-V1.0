---
name: blackeclipse-imprint
description: Follow when creating or modifying BlackEclipse UI to keep the visual identity consistent. Use for any new component, screen, chart, table, or styling change. References the design system and financial UI rules.
---

Follow `skills/IMPRINT.md` whenever creating or modifying BlackEclipse UI. It defines:

- The Bloomberg-inspired dark, green-on-black brand identity
- Design tokens from `src/app/globals.css` (colors, typography, radius)
- Critical global UI overrides (cards = 24px radius, dark `#0f0f0f`; primary buttons = pill; emerald→green, rose→red)
- Component standards (buttons, cards, tables, dialogs, skeletons, empty/error states)
- Financial UI rules (mono numbers, green=positive, red=negative, consistent precision)
- Responsive and accessibility requirements

UI Consistency Rule — before creating a new component, ask:
> "Does BlackEclipse already have a component or pattern for this?"

If yes, reuse it. If no, create a **reusable** component in `src/components/ui/`, not a one-off.

Never introduce arbitrary colors/spacing when an existing token already covers the need. Reuse `src/components/ui/*` primitives.
