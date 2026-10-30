/** E2E 公共辅助：统一门户登录 / 注册与固定账号。 */

import { expect, type Page } from '@playwright/test';

export const TOURIST_URL = 'http://127.0.0.1:5273';
export const CONSOLE_URL = 'http://127.0.0.1:5274';
export const PORTAL_URL = 'http://127.0.0.1:5275/portal/';

export const ADMIN = { phone: '13800000000', password: 'admin123456' };
export const MERCHANT = { phone: '13800000088', password: 'Demo123456' };

/** 游客注册（门户注册成功后切回登录态）。 */
export async function registerTourist(page: Page, phone: string, password = 'e2e123456'): Promise<void> {
  await page.goto(PORTAL_URL);
  await page.getByTestId('mode-register').click();
  await page.getByPlaceholder('11 位手机号').fill(phone);
  await page.getByPlaceholder('至少 6 位').fill(password);
  await page.getByPlaceholder('怎么称呼您').fill('E2E 买家');
  await page.getByTestId('submit').click();
  await expect(page.getByText('注册成功，请登录')).toBeVisible();
}

/** 游客登录：门户登录后带登录态回到游客端。 */
export async function loginTourist(page: Page, phone: string, password: string): Promise<void> {
  await page.goto(PORTAL_URL);
  await page.getByTestId('identity-tourist').click();
  await page.getByPlaceholder('11 位手机号').fill(phone);
  await page.getByPlaceholder('至少 6 位').fill(password);
  await page.getByTestId('submit').click();
  await page.waitForURL((url) => url.port === new URL(TOURIST_URL).port, { timeout: 15_000 });
  await expect(page.getByText('个人中心').first()).toBeVisible();
}

/** 控制台登录（商户 / 企业 / 管理员）：门户登录后带登录态进入控制台。 */
export async function loginConsole(page: Page, phone: string, password: string): Promise<void> {
  await page.goto(PORTAL_URL);
  await page.getByTestId('identity-merchant').click();
  await page.getByPlaceholder('11 位手机号').fill(phone);
  await page.getByPlaceholder('至少 6 位').fill(password);
  await page.getByTestId('submit').click();
  await page.waitForURL((url) => url.port === new URL(CONSOLE_URL).port, { timeout: 15_000 });
  await expect(page.getByText('概览').first()).toBeVisible();
}

/** Element Plus 的确认框（ElMessageBox）点「确定」。 */
export async function confirmMessageBox(page: Page): Promise<void> {
  await page.locator('.el-message-box').getByRole('button', { name: '确定' }).click();
}

/** 生成一个不重复的 11 位手机号（13 开头）。 */
export function uniquePhone(): string {
  return `13${String(Date.now()).slice(-9)}`;
}
