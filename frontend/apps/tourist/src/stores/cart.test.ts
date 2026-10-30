/** 购物车角标 store 测试（数据以服务端为权威）。 */

import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', () => ({
  getCart: vi.fn(),
  hasSession: vi.fn(),
}));

import { getCart, hasSession } from '@qh/api-client';

import { useCartStore } from './cart';

const mockedGetCart = vi.mocked(getCart);
const mockedHasSession = vi.mocked(hasSession);

describe('cart store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it('setFromCart 按条目数更新角标', () => {
    const cart = useCartStore();
    cart.setFromCart({
      items: [
        { id: 1, product_id: 1, name: 'a', price: 1, quantity: 1, amount: 1, stock: 1, available: true },
        { id: 2, product_id: 2, name: 'b', price: 1, quantity: 2, amount: 2, stock: 9, available: true },
      ],
      total_amount: 3,
    });
    expect(cart.count).toBe(2);
  });

  it('未登录时 refresh 直接清零且不发起请求', async () => {
    mockedHasSession.mockReturnValue(false);
    const cart = useCartStore();
    cart.count = 5;

    await cart.refresh();

    expect(cart.count).toBe(0);
    expect(mockedGetCart).not.toHaveBeenCalled();
  });

  it('已登录时 refresh 拉取购物车并更新角标', async () => {
    mockedHasSession.mockReturnValue(true);
    mockedGetCart.mockResolvedValue({
      items: [
        { id: 1, product_id: 1, name: 'a', price: 1, quantity: 1, amount: 1, stock: 1, available: true },
      ],
      total_amount: 1,
    });
    const cart = useCartStore();

    await cart.refresh();

    expect(mockedGetCart).toHaveBeenCalledTimes(1);
    expect(cart.count).toBe(1);
  });

  it('请求失败时清零（不残留旧角标）', async () => {
    mockedHasSession.mockReturnValue(true);
    mockedGetCart.mockRejectedValue(new Error('网络错误'));
    const cart = useCartStore();
    cart.count = 3;

    await cart.refresh();

    expect(cart.count).toBe(0);
  });

  it('clear 清零（退出登录时调用）', () => {
    const cart = useCartStore();
    cart.count = 4;
    cart.clear();
    expect(cart.count).toBe(0);
  });
});
