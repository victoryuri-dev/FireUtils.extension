import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" é essencial pro WebView2 (Fase 3) — o pyRevit vai servir o
// index.html do build via SetVirtualHostNameToFolderMapping, e os assets
// (JS/CSS) precisam de caminho relativo, não absoluto ("/assets/..." só
// funciona se a raiz do host for exatamente "/").
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
  },
});
