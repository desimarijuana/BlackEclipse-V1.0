/**
 * In-memory TTL cache with namespace support.
 * 
 * Designed to be swapped for Redis when scaling up.
 * For now it uses a simple Map with TTL-based eviction.
 */

interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}

class MemoryCache {
  private store = new Map<string, CacheEntry<unknown>>();
  private defaultTTL: number;

  constructor(defaultTTLSeconds = 300) {
    this.defaultTTL = defaultTTLSeconds * 1000;
  }

  /**
   * Get a cached value. Returns undefined if expired or missing.
   */
  get<T>(key: string): T | undefined {
    const entry = this.store.get(key);
    if (!entry) return undefined;
    if (Date.now() > entry.expiresAt) {
      this.store.delete(key);
      return undefined;
    }
    return entry.value as T;
  }

  /**
   * Set a value with optional custom TTL (seconds).
   */
  set<T>(key: string, value: T, ttlSeconds?: number): void {
    const ttl = (ttlSeconds ?? this.defaultTTL / 1000) * 1000;
    this.store.set(key, {
      value,
      expiresAt: Date.now() + ttl,
    });
  }

  /**
   * Delete a specific key.
   */
  delete(key: string): boolean {
    return this.store.delete(key);
  }

  /**
   * Invalidate all keys matching a prefix (e.g. "stocks:US:").
   */
  invalidatePrefix(prefix: string): number {
    let count = 0;
    for (const key of this.store.keys()) {
      if (key.startsWith(prefix)) {
        this.store.delete(key);
        count++;
      }
    }
    return count;
  }

  /**
   * Clear the entire cache.
   */
  clear(): void {
    this.store.clear();
  }

  /**
   * Purge expired entries (call periodically to prevent memory leaks).
   */
  purgeExpired(): number {
    const now = Date.now();
    let count = 0;
    for (const [key, entry] of this.store.entries()) {
      if (now > entry.expiresAt) {
        this.store.delete(key);
        count++;
      }
    }
    return count;
  }

  get size(): number {
    return this.store.size;
  }
}

// ─── Singleton ────────────────────────────────────────────────────────

const globalForCache = globalThis as unknown as {
  dataCache: MemoryCache | undefined;
};

/**
 * Global singleton cache instance.
 * Default TTL: 5 minutes (300s).
 */
export const dataCache =
  globalForCache.dataCache ?? new MemoryCache(300);

if (process.env.NODE_ENV !== "production") {
  globalForCache.dataCache = dataCache;
}

// ─── Helpers ──────────────────────────────────────────────────────────

/** Build a namespaced cache key. */
export function cacheKey(...parts: string[]): string {
  return parts.join(":");
}
