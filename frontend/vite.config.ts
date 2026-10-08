import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :7860 (uvicorn); Vite proxies /api to it so the
// session cookie stays same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:7860", changeOrigin: false } },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
});
