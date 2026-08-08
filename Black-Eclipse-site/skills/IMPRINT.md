# IMPRINT.md — BlackEclipse Design System & Visual Identity

> Follow this file **whenever creating or modifying UI**. It exists to prevent the AI from producing a different-looking interface on every feature.
> Where the codebase conflicts with this file, the **actual implementation** (globals.css, components) is the source of truth until intentionally changed.

---

## Brand Identity

- **Visual identity:** Bloomberg-inspired dark terminal — green-on-black, dense, professional.
- **Design philosophy:** Information-rich, data-first, glassmorphic-but-restrained. Dark, premium, technical.
- **Product personality:** Professional, intelligent, technical, trustworthy, fast.
- **Target experience:** A "quant's command center" — dense data that remains readable, not a generic AI dashboard.

The design should feel: **professional, intelligent, technical, premium, data-dense but readable, consistent, fast, trustworthy.**

Avoid generic "AI dashboard" aesthetics (light cards, pastel gradients, oversized whitespace).

## Design Tokens (actual — from `src/app/globals.css`)

### Colors — dark (default, active)
- `--background: oklch(0 0 0)` (pure black)
- `--foreground: oklch(0.9551 0 0)` (near-white)
- `--card: oklch(0.1448 0 0)` — dark gray card
- `--popover: oklch(0.2210 0.0015 197.0452)`
- `--primary: #7aff78` (lime green — THE accent)
- `--primary-foreground: oklch(0 0 0)` (black on green)
- `--secondary`, `--muted`, `--accent`: dark grays (`oklch(0.18-0.26 ...)`)
- `--muted-foreground: oklch(0.6731 0 0)` — gray secondary text
- `--border: oklch(0.2138 0.0019 286.2347)`
- `--ring: #7aff78` (green focus ring)
- `--destructive: oklch(0.7425 0.1696 1.0847)` — red
- `--chart-1: #7aff78`

### Global UI overrides (critical — do NOT override these with new arbitrary values)
- **Cards** (`.bg-card`, `[class*="bg-card/"]`): `border-radius: 24px !important`, dark: `background: #0f0f0f !important`, `border: 2px solid rgba(255,255,255,0.05) !important`. Hover border → `#7aff78`.
- **Primary buttons** (`button.bg-primary`, `a.bg-primary`): pill (`border-radius: 9999px !important`), dark: `background: rgba(16,16,16,0.9)`, `border: 1px solid rgba(255,255,255,0.12)`, white text.
- **`text-primary`**: gray by default (not green!), turns green on hover. SVGs with `text-primary` are green always.
- **Emerald remap**: `text-emerald-*` → green (`#7aff78` dark); `bg-emerald-500` → `#7aff78`.
- **Rose/red**: `text-rose-*` → `#ff3e3e`; `bg-rose-500` → `#ff3e3e`.

### Typography
- `--font-sans`: system sans stack (also used for headings via `--font-serif` = same stack) — **one font family for body + headings**.
- `--font-mono`: JetBrains Mono / IBM Plex Mono — use for all **prices, numbers, symbols, data**.
- `--radius: 0.6rem`.

### Spacing & shadows
- `--spacing: 0.27rem` (compact density).
- Shadows: layered black shadows; `--radius` drives `sm`/`md`/`lg`/`xl`.

## Components — Standards

- **Buttons:** use `src/components/ui/button.tsx` or the global `bg-primary` pill style. Never hand-roll.
- **Inputs:** `src/components/ui/input.tsx`.
- **Dropdowns/Selects:** `src/components/ui/dropdown-menu.tsx`, `select.tsx`.
- **Cards:** use `bg-card` (auto-rounded 24px, dark `#0f0f0f`).
- **Dialogs:** `src/components/ui/dialog.tsx` (mounted-gate for SSR).
- **Tooltips:** `src/components/ui/tooltip.tsx` (mounted-gate).
- **Tables:** dense, `font-mono` for numeric columns, `border-white/5` row dividers, `text-[11px]`, hover row highlight.
- **Navigation:** `src/components/layout/sidebar.tsx` (collapsible, `bg-card/85`, `w-60`/`w-16`).
- **Loading states:** use `src/components/ui/skeleton.tsx` (neutral black/grey primitives) + `TopLoader`.
- **Empty states:** a centered muted message with the relevant icon.
- **Error states:** `src/components/ui/error-boundary.tsx` fallback.

## Financial UI Rules

- Numbers must be **easy to scan** — use mono font, consistent precision.
- **Positive = green** (`text-emerald-400` / `#7aff78`), **negative = red** (`text-rose-400` / `#ff3e3e`).
- Prices: use appropriate precision (crypto 2-4 decimals, stocks 2 decimals, pennies 2-4).
- Percentages: consistently formatted (e.g. `+2.14%`).
- Dates/timestamps: consistent `toLocaleString` / relative ("12m ago") format.
- Tables prioritize **information density** without becoming unreadable.
- Charts use consistent styling (Recharts + TradingView dark theme).
- Market info has clear hierarchy: symbol > name > price > change.

## Responsive Design

- **Desktop** (default): dense multi-column layout, `max-w-7xl` containers.
- **Tablet:** grid columns collapse (`md:grid-cols-3`, `sm:grid-cols-2`).
- **Mobile:** sidebar becomes a drawer (see sidebar `mobileOpen`), tables scroll horizontally.
- Don't simply shrink desktop layouts — use responsive utility classes already present.

## Accessibility

- Keyboard navigation (buttons, inputs focusable).
- Appropriate contrast (muted text on dark is intentional but keep readable).
- Semantic HTML where possible.
- Accessible labels on interactive controls.
- Visible focus states (`focus-visible:ring-2 focus-visible:ring-ring`).
- `prefers-reduced-motion` consideration for the Aurora animation where practical.

## UI Consistency Rule

**Before creating a new component, ask:**
> "Does BlackEclipse already have a component or pattern for this?"

- **If yes** → reuse it.
- **If no** → create a **reusable** component in `src/components/ui/` (or `screens/` for page-level), not a one-off inline implementation.

Never introduce arbitrary colors or spacing values when an existing token already covers the need.
