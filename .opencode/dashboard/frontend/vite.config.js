import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: ['echarts', 'echarts-for-react', '@uiw/react-codemirror', '@codemirror/lang-markdown'],
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    hmr: {
      overlay: false,
    },
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'echarts-vendor': ['echarts', 'echarts-for-react'],
        },
      },
    },
  },
})
