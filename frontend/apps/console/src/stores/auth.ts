/** 登录态（Pinia）· 管理控制台（商户 / 企业 / 管理员）。 */

import {
  fetchMe,
  hasSession,
  login as apiLogin,
  logout as apiLogout,
  type UserPublic,
} from '@qh/api-client';
import { defineStore } from 'pinia';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as UserPublic | null,
  }),
  getters: {
    isLoggedIn: (state) => state.user !== null,
    isAdmin: (state) => state.user?.role === 'admin',
    isMerchant: (state) =>
      state.user?.role === 'merchant' || state.user?.role === 'enterprise',
    displayName: (state) => state.user?.nickname ?? state.user?.phone ?? '',
  },
  actions: {
    /** 启动时恢复登录态：有令牌才请求用户信息，失败静默。 */
    async restore() {
      if (!hasSession()) {
        return;
      }
      try {
        this.user = await fetchMe();
      } catch {
        this.user = null;
      }
    },
    async login(phone: string, password: string, options: { remember?: boolean } = {}) {
      const data = await apiLogin(phone, password, options);
      this.user = data.user;
    },
    /** 主动拉取当前用户（失败抛错，供页面展示提示）。 */
    async fetchUser() {
      this.user = await fetchMe();
      return this.user;
    },
    async logout() {
      await apiLogout();
      this.user = null;
    },
  },
});
