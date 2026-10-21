// ── The drawn-chart registry ────────────────────────────────────────────────
// A chat chart block is drawn by the Python chart engine (matplotlib) in the
// runtime, and the picture is stored as an ARTIFACT. This registry maps the
// block's id to that artifact's id, so the export helpers can fetch the PNG
// without threading refs through the whole render tree.
//
// Entries are removed on unmount — no leaks.

const artifacts = new Map<string, string>();

/** Record the artifact that holds a chart block's picture. */
export function registerChartArtifact(chartId: string, artifactId: string): void {
  artifacts.set(chartId, artifactId);
}

export function unregisterChart(chartId: string): void {
  artifacts.delete(chartId);
}

/** The artifact id for a chart block, or null when it has none. */
export function getChartArtifact(chartId: string): string | null {
  return artifacts.get(chartId) ?? null;
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
