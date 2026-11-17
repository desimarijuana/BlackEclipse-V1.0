// ── Visual strategy teaching ────────────────────────────────────────────────
// The operator can attach reference pictures ("enter here after the retest",
// "this is the failed breakout I want to avoid"). Bots are multimodal: the
// caption + the image are injected into the bot's decision context and its chat.
//
// The rules are about honesty and size, not vision:
//   * only raster data URLs are accepted (a remote URL can change under us);
//   * a bounded count and byte budget, so a bot never bloats its own definition;
//   * the image is REFERENCE, never market data — the prompt says so, and a run
//     must never cite a picture as a price.

import type { StrategyVisual } from "./types";

export const MAX_VISUALS = 4;
export const MAX_VISUAL_BYTES = 2 * 1024 * 1024;
export const MAX_TOTAL_VISUAL_BYTES = 6 * 1024 * 1024;
export const ALLOWED_VISUAL_MIME: readonly string[] = [
  "image/png",
  "image/jpeg",
  "image/webp",
];

const DATA_URL = /^data:(image\/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)$/i;

export interface VisualInput {
  dataUrl: string;
  caption: string;
  mime?: string;
  bytes?: number;
}

export interface VisualResult {
  visuals: StrategyVisual[];
  error: string | null;
  visual: StrategyVisual | null;
}

/** Decode the declared mime + base64 length without keeping another copy. */
export function inspectDataUrl(dataUrl: string): {
  ok: boolean;
  mime: string;
  bytes: number;
  error: string | null;
} {
  const match = DATA_URL.exec(String(dataUrl ?? "").trim());
  if (!match) {
    return {
      ok: false,
      mime: "",
      bytes: 0,
      error: "That image could not be read. Use a PNG, JPEG or WebP file.",
    };
  }
  const mime = match[1].toLowerCase();
  if (!ALLOWED_VISUAL_MIME.includes(mime)) {
    return {
      ok: false,
      mime,
      bytes: 0,
      error: `Images must be PNG, JPEG or WebP (got ${mime}).`,
    };
  }
  const base64 = match[2].replace(/\s+/g, "");
  const padding = base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0;
  const bytes = Math.max(0, Math.floor((base64.length * 3) / 4) - padding);
  return { ok: true, mime, bytes, error: null };
}

export function totalVisualBytes(visuals: readonly StrategyVisual[]): number {
  return visuals.reduce((sum, visual) => sum + (visual.bytes || 0), 0);
}

/**
 * Validate and append one picture. Every failure is a sentence the UI shows —
 * never a silent drop.
 */
export function addVisual(
  visuals: readonly StrategyVisual[],
  input: VisualInput,
  now: number = Date.now(),
): VisualResult {
  if (visuals.length >= MAX_VISUALS) {
    return {
      visuals: [...visuals],
      error: `A bot can carry up to ${MAX_VISUALS} reference images. Remove one first.`,
      visual: null,
    };
  }
  const inspected = inspectDataUrl(input.dataUrl);
  if (!inspected.ok) {
    return { visuals: [...visuals], error: inspected.error, visual: null };
  }
  if (inspected.bytes > MAX_VISUAL_BYTES) {
    return {
      visuals: [...visuals],
      error: `That image is ${(inspected.bytes / 1024 / 1024).toFixed(1)} MB; the limit is 2 MB.`,
      visual: null,
    };
  }
  if (totalVisualBytes(visuals) + inspected.bytes > MAX_TOTAL_VISUAL_BYTES) {
    return {
      visuals: [...visuals],
      error: "The bot's images would exceed the 6 MB budget. Remove one first.",
      visual: null,
    };
  }
  const caption = String(input.caption ?? "").trim().slice(0, 280);
  const visual: StrategyVisual = {
    id: `vis_${now.toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    dataUrl: input.dataUrl.trim(),
    caption,
    mime: inspected.mime,
    bytes: inspected.bytes,
    addedAt: new Date(now).toISOString(),
  };
  return { visuals: [...visuals, visual], error: null, visual };
}

export function removeVisual(
  visuals: readonly StrategyVisual[],
  id: string,
): StrategyVisual[] {
  return visuals.filter((visual) => visual.id !== id);
}

export function updateVisualCaption(
  visuals: readonly StrategyVisual[],
  id: string,
  caption: string,
): StrategyVisual[] {
  return visuals.map((visual) =>
    visual.id === id ? { ...visual, caption: String(caption).slice(0, 280) } : visual,
  );
}

/**
 * The text block injected into the bot's decision/chat context. It is explicit
 * that the pictures are reference material: a model must not treat a screenshot
 * as a live quote, and must not claim the picture "confirms" the current market.
 */
export function visualTeachingPrompt(visuals: readonly StrategyVisual[]): string {
  if (!visuals.length) return "";
  const lines = visuals.map((visual, index) => {
    const caption = visual.caption.trim() || "No caption.";
    return `  ${index + 1}. ${caption} [${visual.mime}, ${Math.round(visual.bytes / 1024)} KB]`;
  });
  return [
    "The operator attached reference images that teach this strategy:",
    ...lines,
    "Treat them as PATTERN GUIDANCE only. They are not live market data, they may be",
    "out of date, and you must never quote a price from an image or claim the current",
    "market matches it. When an image conflicts with the broker/JDdS data, the data wins",
    "and you say so.",
  ].join("\n");
}

/** A short, honest summary for the detail panel. */
export function visualSummary(visuals: readonly StrategyVisual[]): string {
  if (!visuals.length) return "No reference images.";
  const total = totalVisualBytes(visuals);
  return `${visuals.length} reference image${visuals.length === 1 ? "" : "s"} · ${Math.round(
    total / 1024,
  )} KB`;
}
