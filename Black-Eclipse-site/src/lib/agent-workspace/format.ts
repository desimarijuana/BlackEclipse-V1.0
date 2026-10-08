// ── Agent Workspace — display formatting (pure) ──────────────────────────────
// Small, dependency-free formatters shared by the workspace panels. Kept pure
// and separate so they are unit-tested and never fabricate a value.

/** A conservative duration format — callers pass a real millisecond count. */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

/** Wall-clock elapsed time as `mm:ss` / `h:mm:ss`, from two epoch-ms stamps. */
export function formatElapsed(startMs: number | undefined, nowMs: number): string {
  if (startMs == null) return '';
  const total = Math.max(0, Math.floor((nowMs - startMs) / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** A compact token count: `48.2k`, `1.2M`, or the exact integer under 1000. */
export function formatTokens(n: number | undefined): string {
  if (n == null || !Number.isFinite(n)) return '';
  if (n < 1000) return String(Math.round(n));
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

/** A token count with thousands separators (for a precise detail line). */
export function formatCount(n: number | undefined): string {
  if (n == null || !Number.isFinite(n)) return '';
  return n.toLocaleString();
}

/**
 * Format a USD cost. Returns '' when the runtime did not report one, so the UI
 * shows "Not available" rather than a fabricated $0.00.
 */
export function formatCost(usd: number | undefined, known: boolean): string {
  if (!known || usd == null || !Number.isFinite(usd)) return '';
  if (usd === 0) return '$0.00';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

/** A short `HH:MM:SS` clock label from an epoch-ms stamp. */
export function formatClock(ms: number): string {
  const d = new Date(ms);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** A bounded human file size. */
export function formatBytes(bytes: number | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** The one-character mark for a file-change kind. */
export function changeMark(change: 'added' | 'modified' | 'deleted' | 'renamed'): string {
  return change === 'added' ? 'A' : change === 'deleted' ? 'D' : change === 'renamed' ? 'R' : 'M';
}
