import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const proxyTarget = env.VITE_DEV_PROXY_TARGET?.replace(/\/$/, "")

  return {
    base: "./",
    plugins: [react(), tailwindcss()],
    build: {
      outDir: "../static",
      emptyOutDir: true,
    },
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: proxyTarget
        ? {
            "/c": {
              target: proxyTarget,
              changeOrigin: true,
            },
            "/mcp": {
              target: proxyTarget,
              changeOrigin: true,
            },
          }
        : undefined,
    },
  }
})
