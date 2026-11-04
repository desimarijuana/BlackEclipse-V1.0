// ─── Universe index wire version ─────────────────────────────────────────────
// Bump whenever the wire format of `/api/search/index` changes so stale
// sessionStorage caches are invalidated. ONE declaration, imported by both the
// client (`lib/search/universe.ts`) and the server route — the two used to be
// hand-synced, and drift meant a silent stale cache forever.

export const INDEX_VERSION = '2.0.0';
