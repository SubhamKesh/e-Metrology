/**
 * Build-time server entry. Loaded by scripts/prerender.mjs (through Vite's ssrLoadModule) to turn
 * the public routes into static HTML. Never shipped to the browser.
 *
 * Auth: AuthProvider's effect (token lookup / /auth/me) does not run during renderToString, so the
 * tree renders exactly as an anonymous visitor sees it on first paint, which is also what the client's
 * first render produces (status "loading", no user), so hydration matches. No API calls are made.
 */
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/context/AuthContext";
import App from "./App";

export function render(url: string): string {
  const queryClient = new QueryClient();
  return renderToString(
    <QueryClientProvider client={queryClient}>
      <StaticRouter location={url}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </StaticRouter>
    </QueryClientProvider>,
  );
}

export { buildHead, serializeHead, absoluteUrl } from "@/seo/head";
export { assertValidOrigin, originWarnings } from "@/seo/origin";
export { SEO_ROUTES, SITE, PRERENDER_ROUTES, SHELL_ROUTES, indexableRoutes } from "@/seo/seoConfig";
