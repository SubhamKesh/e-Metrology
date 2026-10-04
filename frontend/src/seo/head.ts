/**
 * Builds the <head> model for a route from seoConfig. Shared by:
 *  - <Seo/> (applies it to document.head on the client)
 *  - scripts/prerender.mjs (serialises it into static HTML)
 */
import { SEO_ROUTES, SITE, type RouteSeo, type SeoRouteKey } from "./seoConfig";
import { normalizeOrigin } from "./origin";

export interface MetaTag {
  name?: string;
  property?: string;
  content: string;
}

export interface HeadModel {
  title: string;
  meta: MetaTag[];
  canonical?: string;
  /** Already-serialised, script-safe JSON strings. */
  jsonLd: string[];
}

/** Absolute URL for a path on the canonical origin. "/" stays "/", others never end in a slash. */
export function absoluteUrl(origin: string, path: string): string {
  const clean = path === "/" ? "/" : path.replace(/\/+$/, "");
  return `${origin}${clean}`;
}

export function robotsContent(indexable: boolean): string {
  return indexable ? "index, follow, max-image-preview:large" : "noindex, nofollow";
}

function safeJson(value: unknown): string {
  // "<" escaped so a stray "</script>" inside content can never end the tag.
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

export function buildHead(key: SeoRouteKey, origin: string): HeadModel {
  const seo = SEO_ROUTES[key] as RouteSeo;
  const base = normalizeOrigin(origin);
  const canonical = seo.indexable && seo.path ? absoluteUrl(base, seo.path) : undefined;
  const image = `${base}${SITE.defaultOgImage}`;
  const ogLocale = SITE.locale.replace("-", "_"); // Open Graph uses en_IN, not en-IN

  const meta: MetaTag[] = [
    { name: "description", content: seo.description },
    { name: "robots", content: robotsContent(seo.indexable) },
    { property: "og:site_name", content: SITE.name },
    { property: "og:locale", content: ogLocale },
    { property: "og:type", content: seo.ogType },
    { property: "og:title", content: seo.title },
    { property: "og:description", content: seo.description },
    { property: "og:image", content: image },
    { property: "og:image:width", content: String(SITE.ogImageWidth) },
    { property: "og:image:height", content: String(SITE.ogImageHeight) },
    { property: "og:image:alt", content: SITE.ogImageAlt },
    { name: "twitter:card", content: SITE.twitterCard },
    { name: "twitter:title", content: seo.title },
    { name: "twitter:description", content: seo.description },
    { name: "twitter:image", content: image },
    { name: "twitter:image:alt", content: SITE.ogImageAlt },
  ];
  if (canonical) meta.push({ property: "og:url", content: canonical });

  return {
    title: seo.title,
    meta,
    canonical,
    jsonLd: seo.jsonLd ? seo.jsonLd(base).map(safeJson) : [],
  };
}

// ---------------------------------------------------------------------------
// Build-time serialisation (used by the prerender script)
// ---------------------------------------------------------------------------

function esc(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function serializeHead(head: HeadModel): string {
  const lines: string[] = [`<title>${esc(head.title)}</title>`];
  for (const m of head.meta) {
    const attr = m.name ? `name="${esc(m.name)}"` : `property="${esc(m.property ?? "")}"`;
    lines.push(`<meta ${attr} content="${esc(m.content)}" data-seo />`);
  }
  if (head.canonical) lines.push(`<link rel="canonical" href="${esc(head.canonical)}" data-seo />`);
  for (const json of head.jsonLd) lines.push(`<script type="application/ld+json" data-seo>${json}</script>`);
  return lines.join("\n    ");
}

// ---------------------------------------------------------------------------
// Client-side application (used by <Seo/>)
// ---------------------------------------------------------------------------

function metaSelector(m: MetaTag): string {
  return m.name ? `meta[name="${m.name}"]` : `meta[property="${m.property}"]`;
}

export function applyHead(head: HeadModel, doc: Document = document): void {
  doc.title = head.title;
  const parent = doc.head;
  const keep = new Set<Element>();

  for (const m of head.meta) {
    let el = parent.querySelector(metaSelector(m));
    if (!el) {
      el = doc.createElement("meta");
      if (m.name) el.setAttribute("name", m.name);
      else el.setAttribute("property", m.property ?? "");
      parent.appendChild(el);
    }
    el.setAttribute("content", m.content);
    el.setAttribute("data-seo", "");
    keep.add(el);
  }

  let link = parent.querySelector('link[rel="canonical"]');
  if (head.canonical) {
    if (!link) {
      link = doc.createElement("link");
      link.setAttribute("rel", "canonical");
      parent.appendChild(link);
    }
    link.setAttribute("href", head.canonical);
    link.setAttribute("data-seo", "");
    keep.add(link);
  }

  const existingLd = Array.from(parent.querySelectorAll('script[type="application/ld+json"][data-seo]'));
  const wanted = [...head.jsonLd];
  for (const el of existingLd) {
    const idx = wanted.indexOf(el.textContent ?? "");
    if (idx >= 0) {
      wanted.splice(idx, 1); // identical tag already present (prerendered) - keep it
      keep.add(el);
    }
  }
  for (const json of wanted) {
    const el = doc.createElement("script");
    el.setAttribute("type", "application/ld+json");
    el.setAttribute("data-seo", "");
    el.textContent = json;
    parent.appendChild(el);
    keep.add(el);
  }

  // Drop tags we manage that this route does not define (e.g. canonical / JSON-LD left over from another route).
  parent.querySelectorAll("[data-seo]").forEach((el) => {
    if (!keep.has(el)) el.remove();
  });
}
