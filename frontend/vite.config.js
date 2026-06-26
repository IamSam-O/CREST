import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: resolve(__dirname, '../public'),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(__dirname, 'index.html'),
      output: {
        // Django templates reference /styles.css via _head.html — keep the name stable
        assetFileNames: (info) =>
          info.name?.endsWith('.css') ? 'styles.css' : 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/accounts': 'http://localhost:8000',
      '/manage': 'http://localhost:8000',
      '/multiplayer': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
