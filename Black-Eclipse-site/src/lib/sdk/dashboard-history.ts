import type { SdkDashboardRevision } from './index';

/** Newest revision first, regardless of the server's order. */
export function sortRevisions(revisions: readonly SdkDashboardRevision[]): SdkDashboardRevision[] {
  return [...revisions].sort((a, b) => b.revision - a.revision);
}

/**
 * The revision an "undo" restores: the newest retained revision strictly older
 * than the current one. Returns null when there is no earlier revision.
 */
export function undoRevision(
  revisions: readonly SdkDashboardRevision[],
  currentRevision?: number,
): SdkDashboardRevision | null {
  const sorted = sortRevisions(revisions);
  if (sorted.length === 0) return null;
  const current = currentRevision ?? sorted[0].revision;
  return sorted.find((entry) => entry.revision < current) ?? null;
}
