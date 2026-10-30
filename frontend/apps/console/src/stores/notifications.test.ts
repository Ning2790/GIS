/** 通知角标 store 测试：并发刷新只采纳最新响应（旧响应不能覆盖新状态）。 */

import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  hasSession: () => true,
  getUnreadNotificationCount: vi.fn(),
}));

import { getUnreadNotificationCount } from '@qh/api-client';

import { useNotificationsStore } from './notifications';

const mockedUnread = vi.mocked(getUnreadNotificationCount);

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
});

describe('通知角标 store', () => {
  it('并发刷新：先发后到的旧响应被丢弃', async () => {
    let resolveFirst: (value: { unread: number }) => void = () => undefined;
    const first = new Promise<{ unread: number }>((resolve) => {
      resolveFirst = resolve;
    });
    mockedUnread.mockReturnValueOnce(first as never);
    mockedUnread.mockResolvedValueOnce({ unread: 0 } as never);

    const store = useNotificationsStore();
    const firstCall = store.refresh();
    const secondCall = store.refresh();
    await secondCall;
    expect(store.unread).toBe(0);

    resolveFirst({ unread: 5 }); // 旧请求晚到：不能把 5 写回角标
    await firstCall;
    expect(store.unread).toBe(0);
  });

  it('refresh 失败保留上一次值（不把取不到当成没有未读）', async () => {
    mockedUnread.mockResolvedValueOnce({ unread: 3 } as never);
    const store = useNotificationsStore();
    await store.refresh();
    expect(store.unread).toBe(3);

    mockedUnread.mockRejectedValueOnce(new Error('network'));
    await store.refresh();
    expect(store.unread).toBe(3);
  });

  it('setUnread / clear 使在途刷新失效', async () => {
    let resolvePending: (value: { unread: number }) => void = () => undefined;
    mockedUnread.mockReturnValueOnce(
      new Promise<{ unread: number }>((resolve) => {
        resolvePending = resolve;
      }) as never,
    );
    const store = useNotificationsStore();
    const pending = store.refresh();
    store.setUnread(0);
    resolvePending({ unread: 4 });
    await pending;
    expect(store.unread).toBe(0);
  });
});
