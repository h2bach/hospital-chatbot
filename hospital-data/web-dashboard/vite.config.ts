import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const proxyTarget = env.VITE_ADMIN_API_TARGET || "http://127.0.0.1:8081"
	const proxy = {
		"/api": { target: proxyTarget, changeOrigin: true },
		"/health": { target: proxyTarget, changeOrigin: true },
	}

  return {
    base: "./",
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 8082,
		strictPort: true,
		proxy,
	},
	preview: {
		host: "127.0.0.1",
		port: 8082,
		strictPort: true,
		proxy,
    },
  }
})
