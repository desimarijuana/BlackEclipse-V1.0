// ─── Story clustering ───────────────────────────────────────────────────────
// Groups near-duplicate headlines (the same story from different outlets) so a
// feed shows ONE card per story with "covered by N sources". Similarity is
// word-level Jaccard over a normalized headline (threshold 0.55) and only
// within a ±36h window.
//
// `sourceCount` is also the corroboration signal used by the importance scorer:
// one outlet's take is not the same as four independent wires reporting it.

export interface ClusterableNewsRow {
  headline: string;
  source: string;
  timestamp: string | Date;
  sourceCount?: number;
  clusterSources?: string[];
}

export function clusterNewsRows<T extends ClusterableNewsRow>(
  rows: T[],
): Array<T & { sourceCount: number; clusterSources: string[] }> {
  const normalize = (h: string) =>
    h.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter((w) => w.length > 3);
  const jaccard = (a: string[], b: string[]) => {
    const sa = new Set(a);
    const sb = new Set(b);
    if (sa.size === 0 || sb.size === 0) return 0;
    let inter = 0;
    for (const w of sa) if (sb.has(w)) inter++;
    return inter / (sa.size + sb.size - inter);
  };

  const feats = rows.map((r) => normalize(r.headline));
  const used = new Array(rows.length).fill(false);
  const clustered: T[] = [];

  for (let i = 0; i < rows.length; i++) {
    if (used[i]) continue;
    const rep = rows[i];
    const sources = new Set<string>([rep.source]);
    used[i] = true;
    const tsI = new Date(rep.timestamp).getTime();
    for (let j = i + 1; j < rows.length; j++) {
      if (used[j]) continue;
      const tsJ = new Date(rows[j].timestamp).getTime();
      if (Math.abs(tsI - tsJ) > 36 * 3600 * 1000) continue;
      if (jaccard(feats[i], feats[j]) >= 0.55) {
        used[j] = true;
        sources.add(rows[j].source);
      }
    }
    rep.sourceCount = sources.size;
    rep.clusterSources = Array.from(sources).slice(0, 5);
    clustered.push(rep);
  }
  return clustered as Array<T & { sourceCount: number; clusterSources: string[] }>;
}
