import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build ra thẳng gói Python để thiết bị edge chỉ cần Python (không cần Node).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/aistaff/kiosk/webui",
    emptyOutDir: true,
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/media": "http://localhost:8000",
      "/tts": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
