import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  css: {
    preprocessorOptions: {
      scss: {
        // Quieter dev logs until theme SCSS migrates off @import / legacy color APIs (Dart Sass 3.0 prep).
        silenceDeprecations: [
          'import',
          'global-builtin',
          'color-functions',
          'if-function',
          'legacy-js-api',
        ],
      },
    },
  },
  server: {
    proxy: {
      '/Auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
