import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { assertValidOrigin } from "./src/seo/origin";

export default defineConfig(({ command, mode }) => {
  // Fail fast: a production build without a valid canonical origin would emit wrong canonical URLs,
  // sitemap and robots.txt. (`vite preview` / `vite dev` are not builds and are unaffected.)
  if (command === "build" && mode === "production") {
    const env = loadEnv(mode, process.cwd(), "VITE_");
    try {
      assertValidOrigin(env.VITE_SITE_URL);
    } catch (err) {
      throw new Error(`\n\n[seo] ${(err as Error).message}\n`);
    }
  }

  // Dev only: run the local UI against a deployed API (e.g. the Render service) without CORS errors.
  // Set DEV_API_PROXY=https://your-api.onrender.com in .env.local and leave VITE_API_BASE_URL empty.
  // Not VITE_-prefixed on purpose, so it can never end up in the browser bundle.
  const devEnv = loadEnv(mode, process.cwd(), "");
  const apiTarget = command === "serve" ? (devEnv.DEV_API_PROXY ?? "").trim().replace(/\/+$/, "") : "";
  let proxy: Record<string, ProxyOptions> | undefined;
  if (apiTarget) {
    // The API sets its refresh cookie as `Secure; SameSite=None` for cross-site production use.
    // Through this same-origin proxy that is unnecessary, and Safari rejects Secure cookies on
    // http://localhost, so relax the flags for local development only.
    const relaxCookies: ProxyOptions["configure"] = (p) => {
      p.on("proxyRes", (res) => {
        const cookies = res.headers["set-cookie"];
        if (cookies) {
          res.headers["set-cookie"] = cookies.map((c) =>
            c.replace(/;\s*secure/i, "").replace(/;\s*samesite=none/i, "; SameSite=Lax"),
          );
        }
      });
    };
    proxy = {
      "/api": { target: apiTarget, changeOrigin: true, secure: true, configure: relaxCookies },
      "/ws": { target: apiTarget, changeOrigin: true, secure: true, ws: true },
    };
    console.log(`[dev] proxying /api and /ws to ${apiTarget}`);
  }

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      proxy,
    },
  };
});
