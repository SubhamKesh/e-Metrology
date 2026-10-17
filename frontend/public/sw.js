/* MaapSetu service worker.
 *
 * What it stores (all static, none of it user data):
 *   - the app shell: the empty HTML page the SPA boots from, so the app can OPEN with no signal
 *   - every built JS/CSS chunk (/assets/*), listed at build time, so every screen can load offline
 *   - icons and fonts
 *
 * SECURITY: this worker NEVER caches API traffic, authenticated responses, certificate PDFs or
 * any non-GET request. Officers' assignment data for offline use is stored by the app itself
 * (see src/lib/offlineCache.ts) and wiped on sign-out, not by this worker.
 *
 * The two placeholders below are filled in by the `sw-precache` plugin in vite.config.ts at
 * build time. In dev they stay empty (the worker is only registered in production builds).
 */
const BUILD_ASSETS = /*__PRECACHE_ASSETS__*/ [];
const BUILD_ID = /*__BUILD_ID__*/ "dev";

const SHELL_CACHE = "maapsetu-shell-v2";
const ASSET_CACHE = "maapsetu-assets-v2";
const OFFLINE_URL = "/offline.html";
const SHELL_PAGES = ["/app-shell.html", "/index.html"]; // first one that exists is the offline fallback
const PRECACHE = [OFFLINE_URL, "/icon-192.png", "/icon-512.png", "/favicon.svg"];
const MANIFEST_KEY = "/__asset-manifest__";
const NAV_TIMEOUT_MS = 5000; // weak signal: don't make the officer wait minutes for a dead connection

async function cacheShellPage(cache, url) {
  const res = await fetch(url, { cache: "reload" });
  if (!res.ok || !(res.headers.get("content-type") || "").includes("text/html")) return;
  // Rebuild the response: a redirected response (cleanUrls) can't be used to answer a navigation.
  const body = await res.blob();
  await cache.put(url, new Response(body, { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } }));
}

async function rememberManifest(assets) {
  let prev = {};
  try {
    const hit = await assets.match(MANIFEST_KEY);
    if (hit) prev = await hit.json();
  } catch (_) {
    prev = {};
  }
  // Keep the previous build's files too, so a screen that is still open on the old build can
  // finish loading its lazy chunks while the new worker takes over.
  const previous = prev.build_id && prev.build_id !== BUILD_ID ? prev.current || [] : prev.previous || [];
  await assets.put(
    MANIFEST_KEY,
    new Response(JSON.stringify({ build_id: BUILD_ID, current: BUILD_ASSETS, previous }), {
      headers: { "Content-Type": "application/json" },
    }),
  );
}

async function pruneAssets() {
  if (BUILD_ASSETS.length === 0) return;
  const assets = await caches.open(ASSET_CACHE);
  let keep = new Set(BUILD_ASSETS);
  try {
    const hit = await assets.match(MANIFEST_KEY);
    if (hit) {
      const m = await hit.json();
      keep = new Set([...(m.current || []), ...(m.previous || [])]);
    }
  } catch (_) {
    return;
  }
  for (const req of await assets.keys()) {
    const path = new URL(req.url).pathname;
    if (path.startsWith("/assets/") && !keep.has(path)) await assets.delete(req);
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const shell = await caches.open(SHELL_CACHE);
      await Promise.allSettled(PRECACHE.map((u) => shell.add(u)));
      await Promise.allSettled(SHELL_PAGES.map((u) => cacheShellPage(shell, u)));

      const assets = await caches.open(ASSET_CACHE);
      await Promise.allSettled(
        BUILD_ASSETS.map(async (u) => {
          if (await assets.match(u)) return; // hashed filenames never change
          const res = await fetch(u);
          if (res.ok) await assets.put(u, res);
        }),
      );
      await rememberManifest(assets);
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => k.startsWith("maapsetu-") && k !== SHELL_CACHE && k !== ASSET_CACHE)
          .map((k) => caches.delete(k)),
      );
      await pruneAssets();
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

// Page navigations: network first. If the network is down or too slow, boot the SPA from the
// cached shell (the app then renders from its own saved data); the plain offline page is the
// last resort. Only the static shell is ever served from cache, never a signed-in page.
async function handleNavigate(req) {
  try {
    return await Promise.race([
      fetch(req),
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), NAV_TIMEOUT_MS)),
    ]);
  } catch (_) {
    const shell = await caches.open(SHELL_CACHE);
    for (const u of SHELL_PAGES) {
      const hit = await shell.match(u);
      if (hit) return hit;
    }
    return (await shell.match(OFFLINE_URL)) || Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Fonts are cross-origin but safe, public and static.
  const isFont = url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com";
  if (url.origin !== self.location.origin && !isFont) return; // API & everything else: network only
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) return;

  if (req.mode === "navigate") {
    event.respondWith(handleNavigate(req));
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
