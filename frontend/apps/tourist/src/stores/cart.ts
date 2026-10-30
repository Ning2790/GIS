/** 购物车角标状态（Pinia）：顶栏数量徽标。
 *
 * 数据以服务端为权威（每次增删改后用接口返回值刷新），登录态变化时重置。
 */

import { getCart, hasSession, type Cart } from '@qh/api-client';
import { defineStore } from 'pinia';

export const useCartStore = defineStore('cart', {
  state: () => ({
    count: 0,
  }),
  actions: {
    setFromCart(cart: Cart) {
      this.count = cart.items.length;
    },
    async refresh() {
      if (!hasSession()) {
        this.count = 0;
        return;
      }
      try {
        const cart = await getCart();
        this.setFromCart(cart);
      } catch {
        this.count = 0;
      }
    },
    clear() {
      this.count = 0;
    },
  },
});
