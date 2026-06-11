import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    watch: {
      // Windows + Docker 바인드 마운트에서 파일 변경 감지가 누락되는 문제 보완
      usePolling: true,
      interval: 300,
    },
  },
})
