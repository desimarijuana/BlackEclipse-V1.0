// ── History formatting ───────────────────────────────────────────────────────
// Pure, deterministic formatting for the run/version history surface. Kept out
// of the component so it is testable and so a timestamp is rendered the same
// way everywhere (UTC, never the host locale).

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '—';
  if (ms < 1_000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1_000).toFixed(1)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1_000);
  return `${minutes}m ${seconds}s`;
}

export function shortHash(hash: string | null | undefined): string {
  if (!hash) return '—';
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash;
}

export function versionLabel(version: number, currentVersion?: number | null): string {
  return currentVersion != null && version === currentVersion ? `v${version} · current` : `v${version}`;
}
