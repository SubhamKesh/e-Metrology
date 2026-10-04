/**
 * Production-like preview of dist/ that follows vercel.json (cleanUrls, rewrites, headers, real 404).
 *
 *   npm run build   (with VITE_SITE_URL set)   then   npm run preview:prod
 *
 * `vite preview` falls back to index.html for every unknown URL, which hides routing problems that
 * only appear on Vercel. This small server reproduces the rules from vercel.json instead.
 * It is an approximation of Vercel for local checking, not a replacement for testing the real deploy.
 * Options: PORT=4173, PREVIEW_API_PROXY=https://your-api.onrender.com (forwards /api and /ws).
 */
import { createServer, request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "dist");
const port = Number(process.env.PORT ?? 4173);
const apiProxy = (process.env.PREVIEW_API_PROXY ?? "").trim().replace(/\/+$/, "");
const config = JSON.parse(readFileSync(join(root, "vercel.json"), "utf8"));

if (!existsSync(join(dist, "index.html"))) {
  console.error("dist/ not found. Run `npm run build` first.");
  process.exit(1);
}

/** Vercel/path-to-regexp style source -> RegExp (supports :name(regex), :name*, :name, raw (regex) groups). */
function sourceToRegExp(source) {
  const pattern = source.replace(/(\/)?:(\w+)(?:\(([^)]+)\))?(\*)?/g, (_m, slash = "", _name, rx, star) => {
    if (star) return `(?:${slash}${rx ?? ".*"})?`; // /:path*  -> optional rest of the path
    return `${slash}${rx ? `(?:${rx})` : "[^/]+"}`; // :id(a|b) or :id
  });
  return new RegExp(`^${pattern}$`);
}
const rewrites = (config.rewrites ?? []).map((r) => ({ re: sourceToRegExp(r.source), destination: r.destination }));
const headerRules = (config.headers ?? []).map((h) => ({ re: sourceToRegExp(h.source), headers: h.headers }));

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
  ".xml": "application/xml", ".txt": "text/plain; charset=utf-8", ".webmanifest": "application/manifest+json",
  ".woff2": "font/woff2", ".map": "application/json",
};

const isFile = (p) => existsSync(p) && statSync(p).isFile();

/** Filesystem lookup with cleanUrls semantics: /x -> x.html or x/index.html. */
function resolveFile(pathname) {
  const safe = normalize(pathname).replace(/^(\.\.[/\\])+/, "");
  const direct = join(dist, safe);
  if (!direct.startsWith(dist)) return null;
  if (extname(safe) && isFile(direct)) return direct;
  if (safe === "/" || safe === "") return join(dist, "index.html");
  for (const candidate of [`${direct}.html`, join(direct, "index.html")]) if (isFile(candidate)) return candidate;
  return null;
}

function proxyTo(req, res) {
  const target = new URL(apiProxy);
  const lib = target.protocol === "https:" ? httpsRequest : httpRequest;
  const headers = { ...req.headers, host: target.host };
  delete headers.origin;
  const upstream = lib({ hostname: target.hostname, port: target.port || undefined, path: req.url, method: req.method, headers }, (up) => {
    const out = { ...up.headers };
    if (out["set-cookie"]) {
      out["set-cookie"] = out["set-cookie"].map((c) => c.replace(/;\s*secure/i, "").replace(/;\s*samesite=none/i, "; SameSite=Lax"));
    }
    res.writeHead(up.statusCode ?? 502, out);
    up.pipe(res);
  });
  upstream.on("error", () => { res.writeHead(502); res.end("Bad gateway"); });
  req.pipe(upstream);
}

function send(req, res, status, file, extra = {}) {
  const { pathname } = new URL(req.url, "http://x");
  const headers = { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream", ...extra };
  for (const rule of headerRules) if (rule.re.test(pathname)) for (const h of rule.headers) headers[h.key] = h.value;
  res.writeHead(status, headers);
  res.end(req.method === "HEAD" ? undefined : readFileSync(file));
}

const server = createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  let pathname = decodeURIComponent(url.pathname);

  if (apiProxy && (pathname.startsWith("/api/") || pathname.startsWith("/ws/"))) return proxyTo(req, res);

  // cleanUrls / trailingSlash:false redirects
  if (pathname !== "/" && pathname.endsWith("/")) {
    res.writeHead(308, { Location: pathname.replace(/\/+$/, "") + url.search });
    return res.end();
  }
  if (pathname.endsWith(".html") && config.cleanUrls) {
    const clean = pathname.replace(/\/index\.html$/, "").replace(/\.html$/, "") || "/";
    res.writeHead(308, { Location: clean + url.search });
    return res.end();
  }

  const file = resolveFile(pathname);
  if (file) return send(req, res, 200, file);

  for (const r of rewrites) {
    if (r.re.test(pathname)) {
      const dest = resolveFile(r.destination);
      if (dest) return send(req, res, 200, dest);
    }
  }
  const notFound = join(dist, "404.html");
  if (isFile(notFound)) return send(req, res, 404, notFound);
  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("Not found");
});

server.listen(port, () => {
  console.log(`\nProduction-like preview of dist/ (follows vercel.json): http://localhost:${port}`);
  if (apiProxy) console.log(`API: /api and /ws are proxied to ${apiProxy}`);
  else console.log("API: not proxied. Set PREVIEW_API_PROXY, or build with VITE_API_BASE_URL pointing at the API (CORS applies).");
});
