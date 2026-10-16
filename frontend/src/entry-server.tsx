/**
 * Build-time server entry. Loaded by scripts/prerender.mjs (through Vite's ssrLoadModule) to turn
 * the public routes into static HTML. Never shipped to the browser.
 *
 * Auth: AuthProvider's effect (token lookup / /auth/me) does not run during renderToString, and the
 * browser's first render is "loading" (Landing renders nothing then), so the provider is seeded as
 * "guest" here to render public pages as an anonymous visitor sees them. The client uses createRoot
 * (not hydrateRoot), so the static markup is simply replaced once the app boots. No API calls are made.
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
        <AuthProvider initialStatus="guest">
          <App />
        </AuthProvider>
      </StaticRouter>
    </QueryClientProvider>,
  );
}

export { buildHead, serializeHead, absoluteUrl } from "@/seo/head";
export { assertValidOrigin, originWarnings } from "@/seo/origin";
export { SEO_ROUTES, SITE, PRERENDER_ROUTES, SHELL_ROUTES, indexableRoutes } from "@/seo/seoConfig";
