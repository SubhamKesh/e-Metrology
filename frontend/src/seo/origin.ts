/**
 * Canonical-origin helpers. Pure (no DOM, no Node, no path aliases) so that
 * vite.config.ts, the prerender script and the client can all import it.
 */

// Never valid as a canonical origin. (*.vercel.app is allowed but warned about, see originWarnings.)
const FORBIDDEN_HOSTS = [/(^|\.)localhost$/i, /^127\./, /^0\.0\.0\.0$/, /^\[?::1\]?$/];

/** Trim whitespace and trailing slashes. Does not validate. */
export function normalizeOrigin(raw: string | undefined | null): string {
  return (raw ?? "").trim().replace(/\/+$/, "");
}

/**
 * Validates a production canonical origin and returns it normalised.
 * Throws an Error with a human-readable message when invalid.
 */
export function assertValidOrigin(raw: string | undefined | null): string {
  const origin = normalizeOrigin(raw);
  const hint =
    "Set VITE_SITE_URL to the production canonical origin, e.g. https://www.example.com " +
    "(https, no path, no trailing slash). In Vercel: Project → Settings → Environment Variables.";
  if (!origin) throw new Error(`VITE_SITE_URL is not set. ${hint}`);
  let url: URL;
  try {
    url = new URL(origin);
  } catch {
    throw new Error(`VITE_SITE_URL="${raw}" is not a valid URL. ${hint}`);
  }
  if (url.protocol !== "https:") throw new Error(`VITE_SITE_URL="${raw}" must use https://. ${hint}`);
  if (url.pathname !== "/" || url.search || url.hash) {
    throw new Error(`VITE_SITE_URL="${raw}" must be an origin only (no path, query or hash). ${hint}`);
  }
  if (FORBIDDEN_HOSTS.some((re) => re.test(url.hostname))) {
    throw new Error(
      `VITE_SITE_URL="${raw}" points at a local host. Use the real public canonical domain. ${hint}`,
    );
  }
  return url.origin;
}

/** Non-fatal advice about a valid origin. */
export function originWarnings(origin: string): string[] {
  const warnings: string[] = [];
  const host = new URL(origin).hostname;
  if (/(^|\.)vercel\.app$/i.test(host)) {
    warnings.push(
      `${host} is a *.vercel.app address. It can be indexed, but a custom domain containing your brand ` +
        `(for example maapsetu.in) is far better for brand searches, and switching later changes every canonical URL.`,
    );
  }
  if (/(^|\.)onrender\.com$/i.test(host)) {
    warnings.push(`${host} is an onrender.com address; prefer your real public domain as the canonical origin.`);
  }
  return warnings;
}
