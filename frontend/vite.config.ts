import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Same-origin deployment: built assets live under /assets and the SPA falls
// back to index.html for any non-API route handled by FastAPI.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      // Forward API calls to the FastAPI backend during dev.
      "/health": "http://localhost:8000",
      "/v1": "http://localhost:8000",
    },
  },
});
