// ── Model recency ranking ───────────────────────────────────────────────────
// The model pickers should lead with the newest ids, not the oldest declared
// sample. Providers are inconsistent: some return a `created` timestamp (OpenAI,
// OpenRouter, Groq, Together, Fireworks, Ollama), some only an ordered list, and
// some declare a static catalog. So ranking is layered:
//
//   1. A provider-supplied `created` timestamp (unix seconds) wins outright.
//   2. Within the SAME family (`gpt-4` / `gpt-5` / `claude-sonnet-4-5`) the
//      highest version tuple wins — this is what makes `gpt-5` outrank `gpt-4.1`.
//   3. A `-latest` marker breaks a version tie (an alias points at the newest).
//   4. Otherwise the incoming order is preserved (stable sort), so a router's
//      own ordering and unknown custom ids are never scrambled.
//
// This is a convenience ordering, never an allowlist.

/** A provider-reported creation time, unix seconds, keyed by model id. */
export type CreatedMap = Record<string, number>;

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function family(id: string): string {
  const lower = id.toLowerCase();
  // The portion before the first digit, trimmed of separators. `gpt-5` →
  // `gpt-`, `openai/gpt-5` → `openai/gpt-`, `claude-sonnet-4-5` → `claude-sonnet-`.
  const idx = lower.search(/\d/);
  const prefix = idx === -1 ? lower : lower.slice(0, idx);
  return prefix.replace(/[-_.\s]+$/, '');
}

function versionTuple(id: string): number[] {
  // Consecutive numeric groups, e.g. `gpt-4.1` → [4, 1],
  // `claude-sonnet-4-5` → [4, 5], `qwen2.5-vl-72b` → [2, 5, 72].
  const matches = id.toLowerCase().match(/\d+/g);
  return matches ? matches.slice(0, 3).map((n) => Number.parseInt(n, 10)) : [];
}

function compareVersions(a: number[], b: number[]): number {
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i += 1) {
    const av = a[i] ?? 0;
    const bv = b[i] ?? 0;
    if (av !== bv) return bv - av;
  }
  return 0;
}

function latestMarker(id: string): number {
  return /(?:^|[-_/])latest(?:$|[-_])/i.test(id) ? 1 : 0;
}

/**
 * Compare two model ids, NEWEST FIRST (negative when `a` should sort before
 * `b`). `created` is optional; when either id has a timestamp it takes
 * precedence over the id heuristic.
 */
export function compareModelRecency(a: string, b: string, created?: CreatedMap): number {
  if (a === b) return 0;

  const ca = asNumber(created?.[a]);
  const cb = asNumber(created?.[b]);
  if (ca !== null && cb !== null && ca !== cb) return cb - ca;
  if (ca !== null && cb === null) return -1;
  if (ca === null && cb !== null) return 1;

  // Different families (a router fronting many vendors) keep their incoming
  // order — comparing `llama-3` to `qwen-2.5` by number is meaningless.
  if (family(a) !== family(b)) return 0;

  const byVersion = compareVersions(versionTuple(a), versionTuple(b));
  if (byVersion !== 0) return byVersion;

  return latestMarker(b) - latestMarker(a);
}

/** Stable, newest-first copy of `models` (duplicates are kept as given). */
export function sortModelsNewestFirst(models: string[], created?: CreatedMap): string[] {
  return [...models].sort((a, b) => compareModelRecency(a, b, created));
}
