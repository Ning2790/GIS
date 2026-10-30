import { fileURLToPath, URL } from 'node:url';

import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig(({ command, isPreview }) => ({
  // 生产由 nginx 挂在 /portal/；开发期仍从根路径访问，便于直接打开 5175。
  // 注意 vite preview 的 command 也是 serve，必须用 isPreview 保留构建时的 base。
  base: command === 'build' || isPreview ? '/portal/' : '/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  preview: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  server: {
    port: 5175,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
}));
