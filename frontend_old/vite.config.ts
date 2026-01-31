import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import vueJsx from '@vitejs/plugin-vue-jsx';
import Components from "unplugin-vue-components/vite";
import AutoImport from "unplugin-auto-import/vite";
import Layouts from "vite-plugin-vue-layouts-next";
import VueRouter from "unplugin-vue-router/vite";
import { VueRouterAutoImports } from "unplugin-vue-router";
import tailwindcss from "@tailwindcss/vite";
import Checker from "vite-plugin-checker";
import { PrimeVueResolver } from "unplugin-vue-components/resolvers";

const DEV_BASE = "/";
const PROD_BASE = "/static/";

export default defineConfig(({ mode }) => {
  const isProd = mode === "production";

  return {
    base: isProd ? PROD_BASE : DEV_BASE,
    // Load .env from frontend directory
    envDir: '.',
    plugins: [
      VueRouter({
        dts: "src/typed-router.d.ts",
      }),
      Layouts(),
      tailwindcss(),
      AutoImport({
        imports: [
          "vue",
          VueRouterAutoImports,
          {
            pinia: ["defineStore", "storeToRefs"],
          },
        ],
        dts: "src/auto-imports.d.ts",
        eslintrc: {
          enabled: true,
        },
        vueTemplate: true,
      }),
      Components({
        resolvers: [PrimeVueResolver()],
        dts: "src/components.d.ts",
      }),
      vue(),
      vueJsx(),
      Checker({ typescript: true }),
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("src", import.meta.url)),
      },
      extensions: [".js", ".json", ".jsx", ".mjs", ".ts", ".tsx", ".vue"],
    },
    server: {
      host: "localhost",
      port: 5173,
      open: true,
      hmr: true,
      proxy: {
        "/api": "http://localhost:8000",
      },
    },
    optimizeDeps: {
      // zachowujemy oba: noDiscovery z nowszego podejścia oraz exclude dla unplugin-vue-router
      noDiscovery: true,
      include: ['leaflet'],
      exclude: [
        "vue-router",
        "unplugin-vue-router/runtime",
        "unplugin-vue-router/data-loaders",
        "unplugin-vue-router/data-loaders/basic",
      ],
    },
    define: { "process.env": {} },
    build: {
      sourcemap: !isProd,
    },
  };
});
