import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts'],
    // 统一桩掉 Element Plus 的命令式 API（ElMessage / ElMessageBox），见 src/test-setup.ts
    setupFiles: ['./src/test-setup.ts'],
  },
});
