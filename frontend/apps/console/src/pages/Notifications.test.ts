/** 消息通知页测试（控制台）：列表渲染 / 未读角标 / 查看详情标已读并跳转 / 全部已读。 */

import { flushPromises, mount } from '@vue/test-utils';
import ElementPlus from 'element-plus';
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
    type: 'order.paid',
    title: '订单已支付',
    content: '订单 #10 已支付 ￥20.00，请及时发货',
    ref_type: 'order',
    ref_id: 10,
    is_read: false,
    created_at: '2026-10-17T10:00:00Z',
    ...overrides,
  };
}

function page(items: unknown[], total?: number) {
  return { items, total: total ?? items.length, page: 1, page_size: 10 } as never;
}

async function mountNotifications() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const wrapper = mount(Notifications, {
    global: { plugins: [ElementPlus, pinia], stubs: { RouterLink: true } },
  });
  await flushPromises();
  return { wrapper, pinia };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedUnread.mockResolvedValue({ unread: 1 } as never);
  mockedRead.mockResolvedValue(notification({ is_read: true }) as never);
  mockedReadAll.mockResolvedValue({ updated: 1 } as never);
});

describe('消息通知页（控制台）', () => {
  it('渲染通知内容与未读角标', async () => {
    mockedList.mockResolvedValue(page([notification()]));
    const { wrapper } = await mountNotifications();

    expect(mockedList).toHaveBeenCalledWith(1, 10);
    const text = wrapper.text();
    expect(text).toContain('订单已支付');
    expect(text).toContain('订单 #10 已支付');
    expect(text).toContain('未读 1');
  });

  it('去订单列表：标记已读、未读数归零并跳转', async () => {
    mockedList.mockResolvedValue(page([notification()]));
    const { wrapper, pinia } = await mountNotifications();

    mockedUnread.mockResolvedValue({ unread: 0 } as never); // 标已读后以服务端为准刷新
    const view = wrapper.findAll('button').find((btn) => btn.text().includes('去订单列表'));
    expect(view).toBeTruthy();
    await view!.trigger('click');
    await flushPromises();

    expect(mockedRead).toHaveBeenCalledWith(1);
    expect(useNotificationsStore(pinia).unread).toBe(0);
    expect(routerMocks.push).toHaveBeenCalledWith('/orders?focus=10');
  });

  it('全部标为已读：调用接口并清空未读数', async () => {
    mockedList.mockResolvedValue(
      page([notification(), notification({ id: 2, title: '订单已发货' })]),
    );
    mockedUnread.mockResolvedValue({ unread: 2 } as never);
    const { wrapper, pinia } = await mountNotifications();

    const readAll = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('全部标为已读'));
    expect(readAll).toBeTruthy();
    await readAll!.trigger('click');
    await flushPromises();

    expect(mockedReadAll).toHaveBeenCalled();
    expect(useNotificationsStore(pinia).unread).toBe(0);
    expect(wrapper.text()).not.toContain('未读 2');
  });
});
