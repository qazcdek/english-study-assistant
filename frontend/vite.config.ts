import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // 개발 중에는 프록시로 붙어 CORS 설정 없이도 동작하게 한다.
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    // 화면에 뭐가 그려졌는지 보려면 DOM 이 필요하다. 브라우저는 안 띄운다.
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // Tailwind 를 테스트에서 돌릴 이유가 없다. 보이는 모양이 아니라 구조를 본다.
    css: false,
  },
})
