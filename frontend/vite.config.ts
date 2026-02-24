import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const apiProxyTarget = env.DEV_API_PROXY_TARGET || 'http://localhost:8000'
  const buildId = String(Date.now())

  return {
    plugins: [react()],
    define: {
      __AIRQMON_BUILD_ID__: JSON.stringify(buildId),
    },
    server: {
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        }
      }
    },
    build: {
      outDir: 'dist'
    }
  }
})
