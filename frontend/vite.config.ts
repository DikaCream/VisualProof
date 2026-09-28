import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// DELIBERATELY no absolute `base`: the build is served from the domain root on
// Vercel, and a hardcoded base is what silently breaks a project-scoped mirror
// (the index loads, every /assets/* request 404s, and the page stays blank).
// If this is ever mirrored under a sub-path, set base to that path here.
export default defineConfig({
  plugins: [react()],
  server: { port: 5183 },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 550,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          genlayer: ["genlayer-js"],
        },
      },
    },
  },
});
