// ── Chart color helpers ──────────────────────────────────────────────────────
// zrender (ECharts) cannot parse oklch() — every color that reaches an ECharts
// option must be a hex/rgba string. These helpers resolve CSS variables and
// convert any modern color function to hex.

import { DEFAULT_CHART_PALETTE } from './chart-palette';
import { getChartPalette } from './chart-palette-store';

export function oklchToHex(input: string): string {
  const m = input.match(/oklch\(\s*([\d.]+)%?\s*([\d.]+)?\s*([\d.-]+)?\s*\)/i);
  if (!m) return input;
  const L = parseFloat(m[1]) / (m[1].includes('%') ? 100 : 1);
  const C = m[2] ? parseFloat(m[2]) : 0;
  const H = m[3] ? parseFloat(m[3]) : 0;
  const hr = (H * Math.PI) / 180;
  const a = Math.cos(hr) * C;
  const b = Math.sin(hr) * C;

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ ** 3, mm = m_ ** 3, s = s_ ** 3;

  const r = 4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s;
  const bl = -0.0041960863 * l - 0.7034186147 * mm + 1.707614701 * s;

  const gamma = (x: number) => (x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055);
  const to255 = (x: number) => Math.round(Math.min(1, Math.max(0, gamma(x))) * 255);
  const hex = (x: number) => to255(x).toString(16).padStart(2, '0');
  return `#${hex(r)}${hex(g)}${hex(bl)}`;
}

export function toChartColor(value: string): string {
  if (!value) return '#888888';
  const v = value.trim();
  if (v.startsWith('oklch')) return oklchToHex(v);
  return v;
}

/** Resolve a CSS custom property (e.g. --primary) to a chart-safe color. */
export function cssVarToHex(name: string, fallback = '#888888'): string {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v ? toChartColor(v) : fallback;
  } catch {
    return fallback;
  }
}

// ── BlackEclipse brand up/down colors ─────────────────────────────────────────
export function brandUpDown(): { up: string; down: string } {
  const { up, down } = typeof window === "undefined" ? DEFAULT_CHART_PALETTE.candles : getChartPalette().candles;
  return { up, down };
}

/** Resolve the current theme's up (green) color. */
export function brandUp(): string {
  return brandUpDown().up;
}

/** Resolve the current theme's down (red) color. */
export function brandDown(): string {
  return brandUpDown().down;
}

