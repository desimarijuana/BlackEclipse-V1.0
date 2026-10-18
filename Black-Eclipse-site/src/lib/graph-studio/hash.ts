// ── Deterministic content hash for workflow versions ─────────────────────────
// A small, dependency-free FNV-1a hash used to give each persisted workflow
// version a stable identity. It is NOT cryptographic — it exists so two saves
// with identical semantic content are recognizable and a version has a cheap,
// reproducible key. Canonical JSON ordering is enforced before hashing so the
// same graph always hashes the same regardless of key insertion order.

/** Stable, key-sorted JSON stringify (recursively). */
export function canonicalStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value ?? null);
  if (Array.isArray(value)) return `[${value.map(canonicalStringify).join(',')}]`;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalStringify(obj[k])}`).join(',')}}`;
}

/** FNV-1a (32-bit) rendered as 8 hex chars, prefixed for clarity. */
export function contentHash(value: unknown): string {
  const text = typeof value === 'string' ? value : canonicalStringify(value);
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `wf_${hash.toString(16).padStart(8, '0')}`;
}
