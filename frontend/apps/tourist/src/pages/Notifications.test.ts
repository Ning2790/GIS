/** 消息通知页测试（游客端）：列表与未读提示 / 查看详情 / 全部已读 / 空态。 */

import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const routerMocks = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRouter: () => ({ push: routerMocks.push }),
}));

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  hasSession: () => true,
  listNotifications: vi.fn(),
  getUnreadNotificationCount: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

import {
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '@qh/api-client';

import { useNotificationsStore } from '../stores/notifications';
import Notifications from './Notifications.vue';

const mockedList = vi.mocked(listNotifications);
const mockedUnread = vi.mocked(getUnreadNotificationCount);
const mockedRead = vi.mocked(markNotificationRead);
const mockedReadAll = vi.mocked(markAllNotificationsRead);

function notification(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    type: 'order.shipped',
    title: '订单已发货',
    content: '订单 #8 已由 顺丰 发出，运单号 SF1234567890',
    ref_type: 'order',
    ref_id: 8,
    is_read: false,
    created_at: '2026-10-17T10:00:00Z',
    ...overrides,
  };
}

function page(items: unknown[], total?: number) {
  return { items, total: total ?? items.length, page: 1, page_size: 10 } as never;
}

const GLOBAL = { stubs: { RouterLink: { template: '<a><slot /></a>' } } };

async function mountNotifications() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const wrapper = mount(Notifications, { global: { ...GLOBAL, plugins: [pinia] } });
  await flushPromises();
  return { wrapper, pinia };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedUnread.mockResolvedValue({ unread: 1 } as never);
  mockedRead.mockResolvedValue(notification({ is_read: true }) as never);
  mockedReadAll.mockResolvedValue({ updated: 1 } as never);
});

describe('消息通知页（游客端）', () => {
  it('渲染通知内容、类型标签与未读计数', async () => {
    mockedList.mockResolvedValue(page([notification()]));
    const { wrapper } = await mountNotifications();

    expect(mockedList).toHaveBeenCalledWith(1, 10);
    const text = wrapper.text();
    expect(text).toContain('订单已发货');
    expect(text).toContain('SF1234567890');
    expect(text).toContain('共 1 条 · 未读 1 条');
  });

  it('空态：没有通知时显示引导文案', async () => {
    mockedList.mockResolvedValue(page([], 0));
    mockedUnread.mockResolvedValue({ unread: 0 } as never);
    const { wrapper } = await mountNotifications();

    expect(wrapper.text()).toContain('还没有通知');
  });

  it('点开未读通知：标已读、未读数刷新并跳到订单详情', async () => {
    mockedList.mockResolvedValue(page([notification()]));
    const { wrapper, pinia } = await mountNotifications();

    mockedUnread.mockResolvedValue({ unread: 0 } as never); // 标已读后以服务端为准刷新
    const item = wrapper.find('.item__button');
    await item.trigger('click');
    await flushPromises();

    expect(mockedRead).toHaveBeenCalledWith(1);
    expect(useNotificationsStore(pinia).unread).toBe(0);
    expect(routerMocks.push).toHaveBeenCalledWith('/orders/8');
  });

  it('全部标为已读：调用接口、清空未读并更新列表状态', async () => {
    mockedList.mockResolvedValue(page([notification(), notification({ id: 2 })]));
    mockedUnread.mockResolvedValue({ unread: 2 } as never);
    const { wrapper, pinia } = await mountNotifications();

    expect(wrapper.text()).toContain('未读 2 条');
    const readAll = wrapper.findAll('button').find((btn) => btn.text().includes('全部标为已读'));
    expect(readAll).toBeTruthy();
    await readAll!.trigger('click');
    await flushPromises();

    expect(mockedReadAll).toHaveBeenCalled();
    expect(useNotificationsStore(pinia).unread).toBe(0);
    expect(wrapper.text()).not.toContain('全部标为已读');
    expect(wrapper.findAll('.item--unread')).toHaveLength(0);
  });
});
