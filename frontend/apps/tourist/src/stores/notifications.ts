/** 站内通知角标状态（Pinia）：顶栏铃铛未读数。
 *
 * 数据以服务端为权威：登录后拉取；页面标记已读后用接口结果同步，
 * 失败静默（角标是增强，不影响主流程）。
 */

import { getUnreadNotificationCount, hasSession } from '@qh/api-client';
import { defineStore } from 'pinia';

export const useNotificationsStore = defineStore('notifications', {
  state: () => ({
    unread: 0,
    // 请求序号：并发 refresh 时只采纳最新一次响应，避免旧响应覆盖新状态
    seq: 0,
  }),
  actions: {
    async refresh() {
      if (!hasSession()) {
        this.unread = 0;
        return;
      }
      const seq = ++this.seq;
      try {
        const { unread } = await getUnreadNotificationCount();
        if (seq === this.seq) {
          this.unread = unread;
        }
      } catch {
        // 网络抖动 / 500 时保留上一次值：不能把「取不到」当成「没有未读」
      }
    },
    setUnread(value: number) {
      this.seq += 1;
      this.unread = Math.max(0, value);
    },
    clear() {
      this.seq += 1;
      this.unread = 0;
    },
  },
});
