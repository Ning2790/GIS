/** 链路③：在线客服——游客发起（AI 应答）→ 转人工 → 商户工作台接入并回复 → 游客看到回复。 */

import { expect, test } from '@playwright/test';

import { CONSOLE_URL, MERCHANT, loginConsole, loginTourist, registerTourist, uniquePhone } from './helpers';

test('客服链路：AI 应答 → 转人工 → 商户接入回复', async ({ browser }) => {
  const phone = uniquePhone();
  const buyerCtx = await browser.newContext();
  const buyer = await buyerCtx.newPage();
  await registerTourist(buyer, phone);
  await loginTourist(buyer, phone, 'e2e123456');

  // ---- 1) 发起会话并收到 AI 应答（默认 mock 模型，文案可预期）----
  await buyer.goto('/cs');
  await buyer.getByRole('button', { name: '＋ 开始新会话' }).click();
  await buyer.getByPlaceholder('输入消息，回车发送').fill('十月去青海湖要带什么衣服？');
  await buyer.getByRole('button', { name: '发送' }).click();
  await expect(buyer.getByText(/已收到您的问题|AI 助手/).first()).toBeVisible();

  // ---- 2) 转人工 → 进入人工队列 ----
  await buyer.getByRole('button', { name: '转人工客服' }).click();
  await expect(buyer.getByText('排队等待人工客服').first()).toBeVisible();

  // ---- 3) 商户在工作台接入并回复 ----
  const merchantCtx = await browser.newContext();
  const merchant = await merchantCtx.newPage();
  await loginConsole(merchant, MERCHANT.phone, MERCHANT.password);
  await merchant.goto(`${CONSOLE_URL}/cs`);
  await expect(merchant.getByText(/人工队列（[1-9]/)).toBeVisible();
  await merchant.getByRole('button', { name: '接入' }).first().click();
  await expect(merchant.getByText(/已接入会话/)).toBeVisible();

  const reply = '十月青海湖白天约 10℃，早晚接近 0℃，建议冲锋衣加抓绒。';
  await merchant.getByPlaceholder('输入回复，回车发送').fill(reply);
  await merchant.getByRole('button', { name: '发送' }).click();

  // ---- 4) 游客端（5 秒轮询）看到人工回复 ----
  await expect(buyer.getByText(/冲锋衣加抓绒/)).toBeVisible({ timeout: 20_000 });
  // 会话状态只在页面动作时刷新（消息是 5 秒轮询）：刷新后应显示已进入人工接待
  await buyer.reload();
  await expect(buyer.getByText('人工客服接待中').first()).toBeVisible();
});
