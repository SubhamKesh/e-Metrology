import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

// Writes the list of built files (/assets/*) into dist/sw.js so the service worker can download
// every JS/CSS chunk at install time. That is what lets each screen open with no signal, even
// the lazy-loaded ones the officer never visited. The same list also gives each deploy its
// own build id, so sw.js changes on every release and browsers pick up the update.
function swPrecache(): Plugin {
  return {
    name: "sw-precache",
    apply: "build",
    writeBundle(options, bundle) {
      const outDir = options.dir ?? path.resolve(__dirname, "dist");
      const swPath = path.join(outDir, "sw.js");
      if (!existsSync(swPath)) return;
      const assets = Object.keys(bundle)
        .filter((f) => f.startsWith("assets/") && !f.endsWith(".map"))
        .map((f) => `/${f}`)
        .sort();
      const buildId = createHash("sha256").update(assets.join("|")).digest("hex").slice(0, 10);
      const src = readFileSync(swPath, "utf8")
        .replace(/\/\*__PRECACHE_ASSETS__\*\/\s*\[\]/, () => JSON.stringify(assets))
        .replace(/\/\*__BUILD_ID__\*\/\s*"dev"/, () => JSON.stringify(buildId));
      writeFileSync(swPath, src);
    },
  };
}

export default defineConfig({
  plugins: [react(), swPrecache()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
  },
  build: {
    rollupOptions: {
      output: {
        // Long-lived vendor chunks cache well across deploys.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
});
