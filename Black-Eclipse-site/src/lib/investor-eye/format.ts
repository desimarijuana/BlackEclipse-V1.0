// ── Investor Eye — formatting helpers (client-safe) ──────────────────────────
// Kept free of server imports so client components can use them without pulling
// Prisma (and `better-sqlite3`) into the browser bundle.

/** ISO timestamp → 'HH:MM UTC'. */
export function formatUtc(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const hh = String(d.getUTCHours()).padStart(2, '0');
    const mm = String(d.getUTCMinutes()).padStart(2, '0');
    return `${hh}:${mm} UTC`;
  } catch {
    return iso;
  }
}

/** Signed percentage, e.g. '+1.24%'. */
export function formatPct(value: number | undefined | null): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

/**
 * Make a provider-generated event title readable.
 *
 * GDELT has no headline, so it synthesizes `ACTOR1 / ACTOR2 — City, Region,
 * Country` (or just `ACTOR` when a row is incomplete). Rendered raw this reads
 * as a code fragment — "POLICE / PHILADELPHIA / UNITED STATES" — which is the
 * single biggest reason the feed looked untrustworthy.
 *
 * This restructures the SAME fields into a sentence without inventing anything:
 *
 *   "ACTOR1 / ACTOR2 — City, Country"  →  "ACTOR1 and ACTOR2 in City, Country"
 *   "ACTOR — City, Country"            →  "ACTOR in City, Country"
 *   "ACTOR"                            →  "ACTOR"
 *
 * Only applies when the title actually matches the synthesized shape; a real
 * headline is returned untouched.
 */
export function formatEventTitle(title: string, placeName?: string): string {
  const raw = (title ?? '').trim();
  if (!raw) return raw;

  // Split the synthesized location suffix from the actor part.
  const dashIdx = raw.search(/\s+[—–]\s+/);
  const actorPart = dashIdx > 0 ? raw.slice(0, dashIdx).trim() : raw;
  const geoPart = dashIdx > 0 ? raw.slice(dashIdx).replace(/^\s+[—–]\s+/, '').trim() : '';

  // The synthesized actor field is slash-separated. A real headline containing
  // a single "/" (e.g. "GDP/CPI") should not be rewritten, so require the shape
  // to look like the provider's: either an explicit geo tail, several
  // slash-separated actors, or a bare actor token that matches the place we
  // already resolved (which means the whole title was just the actor name).
  const actors = actorPart.split(' / ').map((s) => s.trim()).filter(Boolean);
  const bareActorLookalike =
    actors.length === 1 && !geoPart && Boolean(placeName) &&
    actors[0].length <= 48 && !/[.!?]/.test(actors[0]);
  const looksSynthesized =
    actors.length > 0 &&
    actors.every((a) => a.length <= 48) &&
    (dashIdx > 0 || actors.length > 1 || bareActorLookalike);
  if (!looksSynthesized) return raw;

  const actorText =
    actors.length === 1 ? actors[0]
      : actors.length === 2 ? `${actors[0]} and ${actors[1]}`
        : `${actors.slice(0, -1).join(', ')} and ${actors[actors.length - 1]}`;

  // Prefer the structured place when the title's own geo tail is absent.
  const place = geoPart || (placeName ?? '').trim();
  return place ? `${actorText} in ${place}` : actorText;
}

