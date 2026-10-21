// ── The chat chart engine registry ───────────────────────────────────────────
// A chat chart block can be drawn by EITHER engine:
//
//   * `eclipse` — the interactive ECharts chart (the original): a live canvas
//     with a crosshair, a tooltip and a legend.
//   * `python`  — the picture the Python chart engine (matplotlib) draws in
//     the runtime, fetched back as an artifact.
//
// This registry holds BOTH: the live ECharts instance for the interactive
// path, and the artifact id for the drawn path. The export helpers ask both,
// so a chart exports the same way whichever engine drew it.

import type { ECharts } from 'echarts';

const instances = new Map<string, ECharts>();
const artifacts = new Map<string, string>();

/** Register the live ECharts instance of a chart block. */
export function registerChart(id: string, instance: ECharts): void {
  instances.set(id, instance);
}

export function unregisterChart(id: string): void {
  instances.delete(id);
  artifacts.delete(id);
}

export function getChart(id: string): ECharts | null {
  return instances.get(id) ?? null;
}

/** Register the artifact that holds a chart block's drawn picture. */
export function registerChartArtifact(id: string, artifactId: string): void {
  artifacts.set(id, artifactId);
}

/** The artifact id for a drawn chart block, or null when it has none. */
export function getChartArtifact(id: string): string | null {
  return artifacts.get(id) ?? null;
}

/**
 * The chart's PNG bytes, fetched from the Artifact Center.
 *
 * Returns null when the chart was never drawn, or when the artifact cannot be
 * read — a missing picture is reported as missing, never as an empty image.
 */
export async function fetchChartPng(chartId: string): Promise<{ blob: Blob; name: string } | null> {
  const artifactId = getChartArtifact(chartId);
  if (!artifactId) return null;
  try {
    const res = await fetch(`/api/artifacts/${encodeURIComponent(artifactId)}/download`);
    if (!res.ok) return null;
    const blob = await res.blob();
    if (!blob.size) return null;
    return { blob, name: `chart-${artifactId.slice(0, 8)}.png` };
  } catch {
    return null;
  }
}
