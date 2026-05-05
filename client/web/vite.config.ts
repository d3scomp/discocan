import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8765",
      "/ws": {
        target: "ws://localhost:8765",
        ws: true,
      },
    },
  },
  build: {
    outDir: "../discocan/server/static",
    emptyOutDir: true,
  },
});
