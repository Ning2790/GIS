/** 链路①：下单全链路（注册 → 地址簿 → 结算含收货信息 → 支付 → 商户发货 → 签收 → 买家收货 → 申报售后）。 */

import { expect, test } from '@playwright/test';

import {
  ADMIN,
  CONSOLE_URL,
  MERCHANT,
  confirmMessageBox,
  loginConsole,
  loginTourist,
  registerTourist,
  uniquePhone,
} from './helpers';

test('下单全链路：注册 → 地址 → 下单 → 支付 → 发货 → 签收 → 收货 → 售后', async ({
  browser,
}) => {
  const buyerPhone = uniquePhone();
  const buyerCtx = await browser.newContext();
  const buyer = await buyerCtx.newPage();

  // ---- 1) 注册 + 登录（游客端）----
  await registerTourist(buyer, buyerPhone);
  await loginTourist(buyer, buyerPhone, 'e2e123456');

  // ---- 2) 地址簿新增默认地址 ----
  await buyer.goto('/addresses');
  await buyer.getByRole('button', { name: '新增地址' }).click();
  await buyer.getByPlaceholder('收货人姓名').fill('马丽');
  await buyer.getByPlaceholder('11 位手机号').fill('13600001111');
  await buyer
    .getByPlaceholder('省 / 市 / 区 + 详细地址')
    .fill('青海省西宁市城中区 E2E 路 1 号 2 单元 301');
  await buyer.getByRole('button', { name: '保存', exact: true }).click();
  await expect(buyer.getByText('地址已保存')).toBeVisible();
  await expect(buyer.getByText('默认').first()).toBeVisible();  // 地址卡上的「默认」标签（页面上另有同名文案）

  // ---- 3) 商城直购：收货信息自动带出默认地址 ----
  await buyer.goto('/products');
  await buyer.getByRole('link', { name: /E2E 牦牛肉干/ }).first().click();
  await expect(buyer.getByRole('heading', { name: /E2E 牦牛肉干/ })).toBeVisible();
  await buyer.getByRole('button', { name: '填写 / 选择收货信息' }).click();
  await expect(buyer.getByRole('textbox', { name: '收货人' })).toHaveValue('马丽');
  await expect(buyer.getByRole('textbox', { name: '收货地址' })).toHaveValue(/E2E 路 1 号/);
  await buyer.getByRole('button', { name: '立即购买' }).click();
  await expect(buyer).toHaveURL(/\/orders\/\d+$/);
  const orderUrl = buyer.url();
  await expect(buyer.getByText('待支付')).toBeVisible();
  await expect(buyer.getByText(/超时未支付将自动取消/)).toBeVisible();

  // ---- 4) 创建支付单，管理员在控制台模拟回调 ----
  await buyer.getByRole('button', { name: '创建支付单' }).click();
  await expect(buyer.getByText(/支付单已创建/)).toBeVisible();

  const adminCtx = await browser.newContext();
  const admin = await adminCtx.newPage();
  await loginConsole(admin, ADMIN.phone, ADMIN.password);
  await admin.goto(`${CONSOLE_URL}/orders`);
  await admin.getByRole('button', { name: '模拟支付成功' }).first().click();
  await confirmMessageBox(admin);
  await expect(admin.getByText(/已模拟支付成功，订单转为已支付/)).toBeVisible();

  // ---- 5) 商户发货 + 标记签收 ----
  const merchantCtx = await browser.newContext();
  const merchant = await merchantCtx.newPage();
  await loginConsole(merchant, MERCHANT.phone, MERCHANT.password);
  await merchant.goto(`${CONSOLE_URL}/orders`);
  await merchant.getByRole('button', { name: '发货' }).first().click();
  await merchant.getByPlaceholder('如：顺丰').fill('顺丰');
  await merchant.getByPlaceholder('物流单号（不少于 4 位）').fill('SF-E2E-0001');
  await merchant.getByRole('button', { name: '确认发货' }).click();
  await expect(merchant.getByText(/已发货，买家可查看物流并确认收货/)).toBeVisible();
  await expect(merchant.getByText('顺丰 SF-E2E-0001')).toBeVisible();

  await merchant.getByRole('button', { name: '标记签收' }).first().click();
  await confirmMessageBox(merchant);
  await expect(merchant.getByText('已标记签收')).toBeVisible();
  await expect(merchant.getByText(/已签收 20\d{2}\//)).toBeVisible();  // 物流列的签收时间

  // ---- 6) 买家：物流可见 → 确认收货 → 申请售后 ----
  await buyer.goto(orderUrl);
  await expect(buyer.getByText('顺丰 SF-E2E-0001')).toBeVisible();
  buyer.on('dialog', (dialog) => void dialog.accept());
  await buyer.getByRole('button', { name: '确认收货' }).click();
  await expect(buyer.getByText('已完成').first()).toBeVisible();  // 状态标签（页上有两处同名标签）

  await buyer.getByRole('button', { name: '申请售后' }).click();
  await buyer.locator('select.after-sale__select').selectOption('damaged');
  await buyer.getByPlaceholder(/补充说明/).fill('外箱有明显挤压痕迹，内袋漏气');
  await buyer.getByRole('button', { name: '提交售后申请' }).click();
  await expect(buyer).toHaveURL(/\/after-sales\/\d+$/);
  await expect(buyer.getByText('待商户处理')).toBeVisible();
  await expect(buyer.getByText('包装 / 商品破损')).toBeVisible();

  // ---- 7) 商户在售后管理里受理并完成 ----
  await merchant.goto(`${CONSOLE_URL}/after-sales`);
  await merchant.getByRole('button', { name: '处理' }).first().click();
  await merchant.getByRole('button', { name: '受理' }).click();
  await expect(merchant.getByText(/已受理，进入处理中/)).toBeVisible();

  await merchant.getByRole('button', { name: '完成售后' }).click();
  await merchant.locator('.el-message-box textarea').fill('已补发一箱（SF-E2E-0002）');
  await confirmMessageBox(merchant);
  await expect(merchant.getByText('售后已完成')).toBeVisible();

  // ---- 8) 买家侧看到结单与处理记录 ----
  await buyer.reload();
  await expect(buyer.getByText('已解决', { exact: true })).toBeVisible();  // 状态标签（留言里也含「【已解决】」）
});
