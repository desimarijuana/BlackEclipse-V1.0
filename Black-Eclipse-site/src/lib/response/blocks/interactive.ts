// ── `interactive` block schema ───────────────────────────────────────────────
//
// A self-contained interactive app the model authored (HTML/CSS/JS/SVG) and the
// user can operate inline in the chat — a price knob, a VWAP explorer, a doji
// candlestick figure. The renderer composes the source into ONE document and
// mounts it in a sandboxed iframe (`lib/interactive/document.ts`); it never
// injects model markup into the app DOM.
//
// The model NEVER types market prices into an interactive block. When a widget
// needs real data it declares `dataset` and the HOST fetches it through the
// existing read-only market bridge, then injects a provenance-labelled snapshot
// over postMessage. The iframe is offline (`connect-src 'none'`).
//
// Self-contained like every `response/blocks/*` schema (no import back into
// contract.ts — see blocks/model3d.ts for the circular-init reason).

import { z } from 'zod';

const shortString = z.string().max(500);
const idString = z.string().min(1).max(120);

/** Assembled `html + css + js` ceiling. Large enough for a real mini-app, small
 *  enough that a message stays readable and the frame stays cheap. */
export const MAX_INTERACTIVE_BYTES = 200_000;
export const MIN_INTERACTIVE_HEIGHT = 240;
export const MAX_INTERACTIVE_HEIGHT = 900;
export const MAX_INTERACTIVE_BARS = 5000;

/** The only ranges/intervals the host will forward to `/api/price-history`. */
export const INTERACTIVE_RANGES = ['1mo', '3mo', '6mo', '1y', '2y', '5y'] as const;
export const INTERACTIVE_INTERVALS = ['1d', '1wk', '1mo'] as const;

const interactiveDatasetSchema = z.object({
  kind: z.literal('series').default('series'),
  /** The instrument to fetch. The host validates this again before fetching. */
  symbol: z.string().min(1).max(32),
  market: z.string().min(1).max(16).optional(),
  range: z.enum(INTERACTIVE_RANGES).default('6mo'),
  interval: z.enum(INTERACTIVE_INTERVALS).default('1d'),
});

export const interactiveBlock = z
  .object({
    type: z.literal('interactive'),
    id: idString.optional(),
    title: shortString.optional(),
    description: shortString.optional(),
    caption: shortString.optional(),
    height: z
      .number()
      .int()
      .min(MIN_INTERACTIVE_HEIGHT)
      .max(MAX_INTERACTIVE_HEIGHT)
      .default(420),
    /** Body markup. Inline SVG is expected; a full document is defensively
     *  unwrapped to its body by the composer. */
    html: z.string().min(1).max(MAX_INTERACTIVE_BYTES),
    css: z.string().max(MAX_INTERACTIVE_BYTES).optional(),
    js: z.string().max(MAX_INTERACTIVE_BYTES).optional(),
    /** A real market series the host injects at render time. */
    dataset: interactiveDatasetSchema.optional(),
    /** Static, user-supplied constants only (never market prices). Exposed as
     *  `window.ECLIPSE_DATA`. */
    data: z.record(z.string(), z.unknown()).optional(),
    /** `illustrative` marks a widget whose numbers are examples, not data. */
    provenance: z.enum(['illustrative', 'user-provided']).optional(),
  })
  .refine(
    (block) => block.html.length + (block.css?.length ?? 0) + (block.js?.length ?? 0) <= MAX_INTERACTIVE_BYTES,
    { message: `interactive source is too large (max ${MAX_INTERACTIVE_BYTES} chars assembled)` },
  );

export type InteractiveBlock = z.infer<typeof interactiveBlock>;
export type InteractiveDatasetRequest = z.infer<typeof interactiveDatasetSchema>;
