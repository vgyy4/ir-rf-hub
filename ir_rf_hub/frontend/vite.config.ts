import { fileURLToPath, URL } from "node:url";
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
  plugins: [tailwindcss(), svelte()],
  // shadcn-svelte's generated components import from `$lib/...`, the same
  // alias SvelteKit provides by default. This is a plain Vite SPA, so we
  // have to declare it ourselves (mirrored in tsconfig.json's paths).
  resolve: {
    alias: {
      $lib: fileURLToPath(new URL("./src/lib", import.meta.url)),
    },
  },
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
