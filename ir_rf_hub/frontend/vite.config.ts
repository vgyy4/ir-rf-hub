import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

// base: './' matters here -- under HA Ingress this app is served from a
// dynamic, per-session path like /api/hassio_ingress/<token>/, not from
// the domain root, so all built asset URLs must be relative to
// index.html rather than absolute (`/assets/...` would 404 through the
// ingress proxy). Same reasoning applies to API calls -- see src/lib/api.ts.
export default defineConfig({
  base: "./",
  // tailwindcss() must come before svelte() -- see skeleton.dev's Vite+Svelte setup guide.
  plugins: [tailwindcss(), svelte()],
  build: {
    outDir: "../backend/ir_rf_hub/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8099",
    },
  },
});
