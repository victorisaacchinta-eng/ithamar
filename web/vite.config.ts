import { defineConfig } from "vite";

export default defineConfig({
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1600, // the pdf.js worker is large and loads only when the tool is used
  },
});
