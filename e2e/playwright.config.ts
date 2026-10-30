import { defineConfig } from '@playwright/test';

/** N6 · 浏览器端 E2E（三条主链路）。
 *
 * 与开发 / 演示环境**完全隔离**：
 * - 独立 SQLite 临时库（`e2e/.tmp/e2e.db`，globalSetup 每次重建，含迁移与种子）
 * - 独立后端端口 8100（REDIS_URL / MINIO_ENDPOINT 清空，能力自动降级）
 * - 前端跑**构建产物**（`vite preview`，5273 / 5274 / 5275），`/api` 代理经 VITE_API_TARGET 指向测试后端
 *
 * 浏览器用系统 Edge（channel: msedge），无需下载 Chromium。
 * 前置：`pnpm -r build` 产出 dist（`make e2e-web` 已串联）。
 */
const BACKEND_PORT = 8100;
const TOURIST_PORT = 5273;
const CONSOLE_PORT = 5274;
const PORTAL_PORT = 5275;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const TOURIST_URL = `http://127.0.0.1:${TOURIST_PORT}`;
const CONSOLE_URL = `http://127.0.0.1:${CONSOLE_PORT}`;
// portal 构建 base 为 /portal/，预览地址也带这个前缀
const PORTAL_URL = `http://127.0.0.1:${PORTAL_PORT}/portal/`;

export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // 三条链路共用同一个测试库，串行更稳
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  globalSetup: './global-setup.ts',
  use: {
    channel: 'msedge',
    baseURL: TOURIST_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  webServer: [
    {
      command: 'uv run uvicorn app.main:app --port 8100',
      cwd: '../backend',
      url: `${BACKEND_URL}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ...process.env,
        DATABASE_URL: 'sqlite:///../e2e/.tmp/e2e.db',
        REDIS_URL: '',
        MINIO_ENDPOINT: '',
        WEATHER_PROVIDER: 'mock',
      },
    },
    {
      command: `pnpm exec vite preview --host 127.0.0.1 --port ${TOURIST_PORT} --strictPort`,
      cwd: '../frontend/apps/tourist',
      url: TOURIST_URL,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { ...process.env, VITE_API_TARGET: BACKEND_URL },
    },
    {
      command: `pnpm exec vite preview --host 127.0.0.1 --port ${CONSOLE_PORT} --strictPort`,
      cwd: '../frontend/apps/console',
      url: CONSOLE_URL,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { ...process.env, VITE_API_TARGET: BACKEND_URL },
    },
    {
      command: `pnpm exec vite preview --host 127.0.0.1 --port ${PORTAL_PORT} --strictPort`,
      cwd: '../frontend/apps/portal',
      url: PORTAL_URL,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { ...process.env, VITE_API_TARGET: BACKEND_URL },
    },
  ],
});

export const E2E_URLS = { BACKEND_URL, TOURIST_URL, CONSOLE_URL, PORTAL_URL };
