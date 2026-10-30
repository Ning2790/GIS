/** 链路②：景点浏览 → 精选路线详情 → 套用为我的行程 → 行程停靠点编辑。 */

import { expect, test } from '@playwright/test';

import { loginTourist, registerTourist, uniquePhone } from './helpers';

test('旅行链路：景点 → 精选路线套用 → 行程编辑', async ({ page }) => {
  const phone = uniquePhone();
  await registerTourist(page, phone);
  await loginTourist(page, phone, 'e2e123456');

  // ---- 1) 景点列表（种子导入 5 个）与详情 ----
  await page.goto('/attractions');
  await expect(page.getByRole('heading', { name: '景点' })).toBeVisible();
  const firstAttraction = page.locator('a[href^="/attractions/"]').first();
  await expect(firstAttraction).toBeVisible();
  await firstAttraction.click();
  await expect(page).toHaveURL(/\/attractions\/\d+$/);
  await expect(page.getByText(/票种|门票/).first()).toBeVisible();

  // ---- 2) 精选路线：列表 → 详情 → 套用 ----
  await page.goto('/routes');
  await expect(page.getByRole('heading', { name: /精选路线/ })).toBeVisible();
  await page.locator('a[href^="/routes/"]').first().click();
  await expect(page).toHaveURL(/\/routes\/\d+$/);
  await expect(page.getByRole('button', { name: '套用为我的行程' })).toBeVisible();

  await page.getByRole('button', { name: '套用为我的行程' }).click();
  await expect(page).toHaveURL(/\/plan\/\d+$/);
  const planUrl = page.url();
  await expect(page.getByText(/停靠点|每日安排/).first()).toBeVisible();

  // ---- 3) 行程编辑：进入编辑态 → 添加一个停靠点 → 保存 ----
  await page.getByRole('button', { name: '编辑停靠点' }).click();
  const stops = page.locator('li.stops__item');
  const before = await stops.count();
  expect(before).toBeGreaterThan(0);

  await page.locator('select.adder__select').first().selectOption({ index: 1 });
  await page.getByRole('button', { name: '添加' }).click();
  await expect(stops).toHaveCount(before + 1);

  await page.getByRole('button', { name: '保存' }).click();
  await expect(page.locator('.adder')).toHaveCount(0); // 保存成功后退出编辑态
  await expect(page.getByRole('button', { name: '编辑停靠点' })).toBeVisible();

  // ---- 4) 我的行程列表里能看到刚套用的行程 ----
  await page.goto('/plan');
  await expect(page.locator('a[href^="/plan/"]').first()).toBeVisible();
  await page.locator('a[href^="/plan/"]').first().click();
  await expect(page).toHaveURL(planUrl);
});
