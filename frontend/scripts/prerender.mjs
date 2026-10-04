/**
 * Post-build step (runs after `vite build`): turns the SPA build in dist/ into crawlable static output.
 *
 *   dist/index.html, verify/index.html, register/index.html, how-it-works/index.html, about/index.html
 *       -> real page markup (<h1>, content) + route-specific <head> + JSON-LD
 *   dist/login.html, pending.html, change-password.html, unauthorized.html
 *       -> empty root (client-rendered) but correct noindex <head>
 *   dist/app-shell.html   -> generic noindex shell, rewritten to for /app/* and /verify/:certId (see vercel.json)
 *   dist/404.html         -> NotFound UI, served by Vercel with a real 404 status
 *   dist/sitemap.xml, dist/robots.txt
 *
 * Everything is driven by src/seo/seoConfig.ts. Pages are rendered with react-dom/server and
 * StaticRouter; no headless browser, no network, no API data.
 */
process.env.NODE_ENV = "production";

import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "dist");

const HEAD_RE = /<!-- seo:head -->[\s\S]*?<!-- \/seo:head -->/;
const ROOT_EMPTY = '<div id="root"></div>';
const FORBIDDEN = [/localhost/i, /vercel\.app/i];

function fail(msg) {
  throw new Error(msg);
}

const escAttr = (v) => String(v).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const escXml = (v) => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function main() {
  if (!existsSync(join(dist, "index.html"))) fail("dist/index.html not found. Run `vite build` first.");

  const { loadEnv, createServer } = await import("vite");
  const env = loadEnv("production", root, "VITE_");

  const vite = await createServer({
    root,
    mode: "production",
    appType: "custom",
    logLevel: "warn",
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
  });

  try {
    const ssr = await vite.ssrLoadModule("/src/entry-server.tsx");
    const { render, buildHead, serializeHead, absoluteUrl, assertValidOrigin, originWarnings } = ssr;
    const { SEO_ROUTES, PRERENDER_ROUTES, SHELL_ROUTES, indexableRoutes } = ssr;

    let origin;
    try {
      origin = assertValidOrigin(env.VITE_SITE_URL);
    } catch (err) {
      fail(`[seo] ${err.message}`);
    }
    for (const w of originWarnings(origin)) console.warn(`[seo] warning: ${w}`);
    const gsc = (env.VITE_GSC_VERIFICATION ?? "").trim();

    // ---- config sanity (fail the build on SEO regressions) --------------------------------------
    const seenTitles = new Map();
    const seenDescriptions = new Map();
    for (const { key, seo } of indexableRoutes()) {
      if (seo.title.length > 60) fail(`[seo] title for "${key}" is ${seo.title.length} chars (max 60): ${seo.title}`);
      if (seo.description.length < 120 || seo.description.length > 160) {
        fail(`[seo] description for "${key}" is ${seo.description.length} chars (want 120-160)`);
      }
      if (seenTitles.has(seo.title)) fail(`[seo] duplicate title on "${key}" and "${seenTitles.get(seo.title)}"`);
      if (seenDescriptions.has(seo.description)) fail(`[seo] duplicate description on "${key}"`);
      seenTitles.set(seo.title, key);
      seenDescriptions.set(seo.description, key);
    }

    // ---- html assembly ----------------------------------------------------------------------------
    const template = readFileSync(join(dist, "index.html"), "utf8");
    if (!HEAD_RE.test(template)) fail("[seo] <!-- seo:head --> markers missing from dist/index.html (check index.html).");
    if (!template.includes(ROOT_EMPTY)) fail(`[seo] ${ROOT_EMPTY} not found in dist/index.html.`);

    const gscTag = gsc ? `\n    <meta name="google-site-verification" content="${escAttr(gsc)}" />` : "";

    function page(key, appHtml) {
      const head = serializeHead(buildHead(key, origin)) + gscTag;
      return template
        .replace(HEAD_RE, () => head)
        .replace(ROOT_EMPTY, () => `<div id="root">${appHtml}</div>`);
    }

    function write(rel, content) {
      const file = join(dist, rel);
      mkdirSync(dirname(file), { recursive: true });
      writeFileSync(file, content);
    }

    const report = [];

    // 1. Prerendered public pages
    for (const route of PRERENDER_ROUTES) {
      const appHtml = render(route);
      const h1Count = (appHtml.match(/<h1[\s>]/g) ?? []).length;
      if (h1Count !== 1) fail(`[seo] ${route} renders ${h1Count} <h1> elements (expected exactly 1).`);
      if (appHtml.length < 500) fail(`[seo] ${route} rendered suspiciously little markup.`);
      const html = page(route, appHtml);
      if (SEO_ROUTES[route].jsonLd && !html.includes("application/ld+json")) fail(`[seo] JSON-LD missing on ${route}.`);
      write(route === "/" ? "index.html" : `${route.slice(1)}/index.html`, html);
      report.push(`prerendered   ${route}`);
    }

    // 2. Client-only utility routes: correct noindex head, empty root
    for (const route of SHELL_ROUTES) {
      write(`${route.slice(1)}.html`, page(route, ""));
      report.push(`noindex shell ${route}`);
    }

    // 3. Generic shell for /app/* and /verify/:certId, and the 404 page
    write("app-shell.html", page("shell", ""));
    report.push("noindex shell /app/*, /verify/:certId  (app-shell.html)");
    write("404.html", page("notFound", render("/404")));
    report.push("404 page       404.html");

    // 4. sitemap.xml: only indexable, canonical URLs
    const urls = indexableRoutes().map(({ seo }) => {
      const parts = [`    <loc>${escXml(absoluteUrl(origin, seo.path))}</loc>`];
      if (seo.lastmod) parts.push(`    <lastmod>${seo.lastmod}</lastmod>`);
      if (seo.changefreq) parts.push(`    <changefreq>${seo.changefreq}</changefreq>`);
      if (seo.priority !== undefined) parts.push(`    <priority>${seo.priority.toFixed(1)}</priority>`);
      return `  <url>\n${parts.join("\n")}\n  </url>`;
    });
    write(
      "sitemap.xml",
      `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>\n`,
    );

    // 5. robots.txt
    write(
      "robots.txt",
      [
        "User-agent: *",
        "Allow: /",
        "Disallow: /app/",
        "Disallow: /verify/",
        "",
        `Sitemap: ${origin}/sitemap.xml`,
        "",
      ].join("\n"),
    );

    // ---- final guard: no local / preview hostnames in anything we emit ----------------------------
    const textExt = /\.(html|xml|txt|webmanifest)$/;
    (function scan(dir) {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) scan(p);
        else if (textExt.test(name)) {
          // The configured canonical origin itself is allowed to contain whatever the owner chose.
          const text = readFileSync(p, "utf8").split(origin).join("");
          for (const re of FORBIDDEN) if (re.test(text)) fail(`[seo] ${p.replace(dist, "dist")} contains "${re.source}".`);
        }
      }
    })(dist);

    console.log(`\n[seo] prerender complete for ${origin}`);
    for (const line of report) console.log(`  - ${line}`);
    console.log("  - sitemap.xml, robots.txt\n");
  } finally {
    await vite.close();
  }
}

main().catch((err) => {
  console.error(`\n${err.message ?? err}\n`);
  process.exit(1);
});
