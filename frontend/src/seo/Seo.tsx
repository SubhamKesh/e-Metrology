import { useEffect } from "react";
import { applyHead, buildHead } from "./head";
import { normalizeOrigin } from "./origin";
import type { SeoRouteKey } from "./seoConfig";

/** Canonical origin. Production builds always have VITE_SITE_URL (the build fails otherwise). */
export function getSiteOrigin(): string {
  const fromEnv = normalizeOrigin(import.meta.env.VITE_SITE_URL as string | undefined);
  if (fromEnv) return fromEnv;
  // Dev-only convenience so `npm run dev` works without configuring anything.
  if (import.meta.env.DEV && typeof window !== "undefined") return window.location.origin;
  return "";
}

/**
 * Sets <title>, description, canonical, robots, Open Graph, Twitter tags and JSON-LD for a route.
 * All values come from src/seo/seoConfig.ts. Renders nothing (prerendered heads are built by the
 * prerender script from the same config).
 */
export function Seo({ route }: { route: SeoRouteKey }) {
  useEffect(() => {
    applyHead(buildHead(route, getSiteOrigin()));
  }, [route]);
  return null;
}
