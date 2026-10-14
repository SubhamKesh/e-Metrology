/* MaapSetu service worker — app-shell caching only.
 *
 * SECURITY: this worker NEVER caches API traffic, authenticated responses,
 * certificate PDFs or any non-GET request. Only static app files are cached,
 * so no personal or certificate data is ever stored by the worker.
 * Bump CACHE_VERSION to invalidate old caches on release.
 */
const CACHE_VERSION = "v1";
const SHELL_CACHE = `maapsetu-shell-${CACHE_VERSION}`;
const ASSET_CACHE = `maapsetu-assets-${CACHE_VERSION}`;
const OFFLINE_URL = "/offline.html";

const PRECACHE = [OFFLINE_URL, "/icon-192.png", "/icon-512.png", "/favicon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((c) => c.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("maapsetu-") && k !== SHELL_CACHE && k !== ASSET_CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Fonts are cross-origin but safe, public and static.
  const isFont = url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com";
  if (url.origin !== self.location.origin && !isFont) return; // API & everything else: network only
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) return;

  // Page navigations: network first, offline page when the network is down.
  // The HTML is never stored, so signed-in views are never served stale.
  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  // Hashed build assets and fonts: cache first (immutable).
  if (url.pathname.startsWith("/assets/") || isFont) {
    event.respondWith(
      caches.open(ASSET_CACHE).then(async (cache) => {
        const hit = await cache.match(req);
        if (hit) return hit;
        const res = await fetch(req);
        if (res.ok || res.type === "opaque") cache.put(req, res.clone());
        return res;
      }),
    );
    return;
  }

  // Other static files (icons, manifest, logos): stale-while-revalidate.
  if (/\.(png|svg|ico|webmanifest|jpg|jpeg|webp)$/.test(url.pathname)) {
    event.respondWith(
      caches.open(SHELL_CACHE).then(async (cache) => {
        const hit = await cache.match(req);
        const net = fetch(req)
          .then((res) => {
            if (res.ok) cache.put(req, res.clone());
            return res;
          })
          .catch(() => hit);
        return hit || net;
      }),
    );
  }
});
