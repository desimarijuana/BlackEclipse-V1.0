// ── Investor Eye — time formatting ───────────────────────────────────────────
// One place that turns an instant into what the operator sees, so a timestamp is
// never rendered differently in two panels.
//
// WHY this module exists (two real bugs it fixes):
//
// 1. `formatUtc` returns a SHORT display string ("21:30 UTC"), but callers were
//    doing `formatUtc(x).slice(11, 16)` — they were written expecting an ISO
//    string. That slice is always empty, so source times in the dossier, the
//    timeline and the live feed rendered BLANK. Slicing a formatted string was
//    never the right call; use `formatClock`.
//
// 2. Everything was hard-coded to UTC. Operators reason in their own session
//    timezone, so a fixed UTC clock made "when did this happen" need mental
//    arithmetic. Every function here takes an explicit timezone, and the zone is
//    ALWAYS printed with the time so an unlabelled clock is impossible.
//
// Server-safe: `Intl.DateTimeFormat` needs no DOM, so this is importable from
// route handlers and components alike.

/** The zone used when the caller has no preference. */
export const DEFAULT_TIMEZONE = 'UTC';

/** A short zone label for a clock, e.g. 'UTC' | 'GMT+5' | 'EDT'. */
export function zoneAbbrev(iso: string | null | undefined, timeZone: string = DEFAULT_TIMEZONE): string {
  const d = parse(iso);
  if (!d) return timeZone === 'UTC' ? 'UTC' : timeZone;
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone,
      timeZoneName: 'short',
    }).formatToParts(d);
    return parts.find((p) => p.type === 'timeZoneName')?.value ?? timeZone;
  } catch {
    return timeZone;
  }
}

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

function safeZone(timeZone: string): string {
  try {
    // Throws for an invalid IANA name.
    new Intl.DateTimeFormat('en-US', { timeZone });
    return timeZone;
  } catch {
    return DEFAULT_TIMEZONE;
  }
}

/** 'HH:MM' in the given zone (no label — use `formatClock` for display). */
export function timeInZone(iso: string | null | undefined, timeZone: string = DEFAULT_TIMEZONE): string {
  const d = parse(iso);
  if (!d) return '';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: safeZone(timeZone),
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(d);
  } catch {
    return '';
  }
}

/**
 * The canonical clock for an instant: 'HH:MM ZONE', e.g. '21:30 UTC' or
 * '02:30 GMT+5'. The zone is always present, so a bare time is never shown.
 */
export function formatClock(iso: string | null | undefined, timeZone: string = DEFAULT_TIMEZONE): string {
  const t = timeInZone(iso, timeZone);
  if (!t) return '—';
  return `${t} ${zoneAbbrev(iso, safeZone(timeZone))}`;
}

/**
 * Backwards-compatible UTC clock. Kept because it is used widely and its
 * contract ('HH:MM UTC') is asserted by tests; prefer `formatClock` in new code.
 */
export function formatUtc(iso: string | null | undefined): string {
  return formatClock(iso, 'UTC');
}

/** Full date + time with zone, for detail views: '16 Sep 21:30 UTC'. */
export function formatDateTime(iso: string | null | undefined, timeZone: string = DEFAULT_TIMEZONE): string {
  const d = parse(iso);
  if (!d) return '—';
  const zone = safeZone(timeZone);
  try {
    const date = new Intl.DateTimeFormat('en-GB', {
      timeZone: zone, day: '2-digit', month: 'short',
    }).format(d);
    return `${date} ${formatClock(iso, zone)}`;
  } catch {
    return formatClock(iso, 'UTC');
  }
}

/** A compact 'YYYY-MM-DD HH:MM' for chart axes and tooltips. */
export function formatAxisTime(iso: string | null | undefined, timeZone: string = DEFAULT_TIMEZONE): string {
  const d = parse(iso);
  if (!d) return '';
  const zone = safeZone(timeZone);
  try {
    const day = new Intl.DateTimeFormat('en-CA', {
      timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(d);
    return `${day} ${timeInZone(iso, zone)}`;
  } catch {
    return '';
  }
}

/**
 * A relative age ('4m ago', '2h ago') computed against a supplied `now`, so the
 * result is deterministic in tests and never drifts with the wall clock.
 */
export function relativeAge(iso: string | null | undefined, now: number = Date.now()): string {
  const d = parse(iso);
  if (!d) return '—';
  const sec = Math.max(0, Math.round((now - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
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
