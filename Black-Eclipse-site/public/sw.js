/*
 * BlackEclipse service worker — the "app is stopped" page.
 *
 * Why this exists: when the local server stops (the desktop launcher killed it,
 * `black stop`, a crash), the origin REFUSES the connection and the browser
 * paints its own error page (`ERR_CONNECTION_REFUSED`). No server means no app
 * code can run — except a service worker, which is already installed in this
 * origin and can answer a failed navigation from its own cache.
 *
 * Scope is deliberately tiny:
 *   * it only handles PAGE NAVIGATIONS (`request.mode === 'navigate'`),
 *   * it never touches API calls, chunks, assets, WebSockets or POSTs,
 *   * a 4xx passes through untouched (login redirects, canonical-host
 *     redirects, not-found pages are the app's business),
 *   * a network failure or a 502 (`local-proxy.js` answering while Next is
 *     down) is answered with the cached branded `/offline` page.
 *
 * The offline document itself is rendered by `src/app/offline/route.ts` with the
 * user's saved theme; this file only stores and serves it.
 *
 * Bump CACHE_VERSION whenever the page or the routing rules change: the old
 * cache is deleted on activate.
 */

const CACHE_VERSION = "v1";
const CACHE_NAME = `be-offline-${CACHE_VERSION}`;
const OFFLINE_URL = "/offline";
// A successful page load refreshes the cached copy at most this often, so a
// theme change reaches the offline page without re-fetching on every navigation.
const REFRESH_EVERY_MS = 5 * 60 * 1000;

let lastRefresh = 0;

async function cacheOfflinePage() {
  const cache = await caches.open(CACHE_NAME);
  // `cache: 'reload'` bypasses the HTTP cache so a stale page is never pinned.
  await cache.add(new Request(OFFLINE_URL, { cache: "reload" }));
}

async function offlineResponse() {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(OFFLINE_URL);
  return cached || null;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      try {
        await cacheOfflinePage();
      } catch {
        // First install on a flaky boot: the next successful navigation retries.
      }
      await self.skipWaiting();
    })()
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key.startsWith("be-offline-") && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || request.mode !== "navigate") return;

  event.respondWith(
    (async () => {
      try {
        const response = await fetch(request);
        // 502 is the local proxy's "the app behind me is not answering". Any
        // other status — including the app's own 4xx/5xx pages — is the app
        // speaking, so it passes through untouched and a real error is never
        // disguised as "offline".
        if (response && response.status !== 502) {
          // The app is up: keep the cached offline page in step with the theme.
          // Fire-and-forget (never delays or blocks the navigation) and
          // throttled, so a theme change reaches the offline page within a few
          // minutes without a fetch on every page load.
          const now = Date.now();
          if (response.status < 400 && now - lastRefresh > REFRESH_EVERY_MS) {
            lastRefresh = now;
            cacheOfflinePage().catch(() => {});
          }
          return response;
        }
        return (await offlineResponse()) || response;
      } catch {
        const cached = await offlineResponse();
        if (cached) return cached;
        // Nothing cached yet (first-ever visit): let the browser report the
        // failure honestly rather than inventing a page.
        throw new Error("offline page not cached");
      }
    })()
  );
});
