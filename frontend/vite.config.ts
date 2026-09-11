import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "../src/py_st/services/ui",
    emptyOutDir: true,
    lib: {
      entry: "src/main.tsx",
      name: "FlightLedgerUI",
      formats: ["iife"],
      fileName: () => "shell.js",
      cssFileName: "shell",
    },
  },
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
});
