/** 订单管理页测试：列表渲染 / 状态映射 / 发货对话框校验与提交 / 标记签收 / 管理员模拟回调。 */

const routeState = vi.hoisted(() => ({ query: {} as Record<string, string> }));

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => routeState,
}));

import { flushPromises, mount } from '@vue/test-utils';
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  deliverOrder: vi.fn(),
  exportOrdersCsv: vi.fn(),
  getOrderDetail: vi.fn(),
  listMerchantOrders: vi.fn(),
  paymentCallback: vi.fn(),
  refundPayment: vi.fn(),
  shipOrder: vi.fn(),
}));

import {
  deliverOrder,
  exportOrdersCsv,
  getOrderDetail,
  listMerchantOrders,
  paymentCallback,
  refundPayment,
  shipOrder,
} from '@qh/api-client';

import { useAuthStore } from '../stores/auth';
import Orders from './Orders.vue';

const mockedList = vi.mocked(listMerchantOrders);
const mockedExport = vi.mocked(exportOrdersCsv);
const mockedShip = vi.mocked(shipOrder);
const mockedDeliver = vi.mocked(deliverOrder);
const mockedDetail = vi.mocked(getOrderDetail);
const mockedCallback = vi.mocked(paymentCallback);
const mockedRefund = vi.mocked(refundPayment);
const mockedMessage = vi.mocked(ElMessage);
const mockedBox = vi.mocked(ElMessageBox);

function order(overrides: Record<string, unknown> = {}) {
  return {
    id: 101,
    user_id: 5,
    merchant_id: 9,
    amount: 138,
    status: 'paid',
    expire_at: null,
    cancel_reason: null,
    receiver_name: '马丽',
    receiver_phone: '13800000000',
    receiver_address: '青海省西宁市城中区南关街 12 号',
    shipped_at: null,
    carrier: null,
    tracking_no: null,
    delivered_at: null,
    completed_at: null,
    created_at: '2026-10-15T10:00:00Z',
    paid_at: '2026-10-15T10:05:00Z',
    ...overrides,
  };
}

function page(items: unknown[], total?: number) {
  return { items, total: total ?? items.length, page: 1, page_size: 10 } as never;
}

async function mountOrders(role = 'merchant', userId = 9) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().user = {
    id: userId,
    phone: '13900000001',
    role,
    status: 'active',
    nickname: '验证商户',
    license_no: null,
    created_at: '2026-01-01T00:00:00Z',
  } as never;
  const wrapper = mount(Orders, { global: { plugins: [ElementPlus, pinia] } });
  await flushPromises();
  return wrapper;
}

function buttonWithText(wrapper: Awaited<ReturnType<typeof mountOrders>>, text: string) {
  return wrapper.findAll('button').find((button) => button.text().trim() === text);
}

beforeEach(() => {
  vi.clearAllMocks();
  routeState.query = {};
  mockedList.mockResolvedValue(page([]));
  document.body.innerHTML = '';
});

describe('订单管理页（控制台）', () => {
  it('加载订单列表并渲染行、收货信息与状态文案', async () => {
    mockedList.mockResolvedValue(
      page([
        order(),
        order({
          id: 102,
          status: 'shipped',
          carrier: '顺丰',
          tracking_no: 'SF9988',
          shipped_at: '2026-10-15T11:00:00Z',
        }),
        order({ id: 103, status: 'completed', completed_at: '2026-10-15T12:00:00Z' }),
      ]),
    );
    const wrapper = await mountOrders();

    expect(mockedList).toHaveBeenCalledWith(1, 10);
    const text = wrapper.text();
    expect(text).toContain('101');
    expect(text).toContain('已支付');
    expect(text).toContain('已发货');
    expect(text).toContain('已完成');
    expect(text).toContain('马丽');
    expect(text).toContain('顺丰 SF9988');
  });

  it('加载失败时展示错误提示', async () => {
    mockedList.mockRejectedValue(new Error('服务异常'));
    const wrapper = await mountOrders();

    expect(wrapper.text()).toContain('服务异常');
  });

  it('已支付订单显示「发货」按钮，点击后打开发货对话框并带出订单信息', async () => {
    mockedList.mockResolvedValue(page([order()]));
    const wrapper = await mountOrders();

    const button = buttonWithText(wrapper, '发货');
    expect(button).toBeTruthy();
    await button?.trigger('click');
    await flushPromises();

    const vm = wrapper.vm as unknown as { shipDialog: boolean; shipTarget: { id: number } | null };
    expect(vm.shipDialog).toBe(true);
    expect(vm.shipTarget?.id).toBe(101);
  });

  it('发货校验：承运商为空时提示且不调用接口', async () => {
    mockedList.mockResolvedValue(page([order()]));
    const wrapper = await mountOrders();
    const vm = wrapper.vm as unknown as {
      shipTarget: { id: number } | null;
      shipForm: { carrier: string; trackingNo: string };
      submitShip: () => Promise<void>;
    };
    vm.shipTarget = { id: 101 };
    vm.shipForm.carrier = '';
    vm.shipForm.trackingNo = 'SF1234567890';

    await vm.submitShip();

    expect(mockedMessage.warning).toHaveBeenCalled();
    expect(mockedShip).not.toHaveBeenCalled();
  });

  it('发货校验：运单号不足 4 位时提示且不调用接口', async () => {
    mockedList.mockResolvedValue(page([order()]));
    const wrapper = await mountOrders();
    const vm = wrapper.vm as unknown as {
      shipTarget: { id: number } | null;
      shipForm: { carrier: string; trackingNo: string };
      submitShip: () => Promise<void>;
    };
    vm.shipTarget = { id: 101 };
    vm.shipForm.carrier = '顺丰';
    vm.shipForm.trackingNo = '12';

    await vm.submitShip();

    expect(mockedMessage.warning).toHaveBeenCalled();
    expect(mockedShip).not.toHaveBeenCalled();
  });

  it('发货成功：按填写内容调用接口、提示并刷新列表', async () => {
    mockedList.mockResolvedValue(page([order()]));
    mockedShip.mockResolvedValue(order({ status: 'shipped' }) as never);
    const wrapper = await mountOrders();
    const vm = wrapper.vm as unknown as {
      shipTarget: { id: number } | null;
      shipForm: { carrier: string; trackingNo: string };
      shipDialog: boolean;
      submitShip: () => Promise<void>;
    };
    vm.shipTarget = { id: 101 };
    vm.shipForm.carrier = '顺丰';
    vm.shipForm.trackingNo = 'SF1234567890';

    await vm.submitShip();
    await flushPromises();

    expect(mockedShip).toHaveBeenCalledWith(101, '顺丰', 'SF1234567890');
    expect(mockedMessage.success).toHaveBeenCalled();
    expect(vm.shipDialog).toBe(false);
    expect(mockedList).toHaveBeenCalledTimes(2); // 初始加载 + 发货后刷新
  });

  it('已签收或已完成的订单不再显示发货 / 签收按钮', async () => {
    mockedList.mockResolvedValue(
      page([
        order({ id: 104, status: 'shipped', delivered_at: '2026-10-15T11:30:00Z' }),
        order({ id: 105, status: 'completed' }),
      ]),
    );
    const wrapper = await mountOrders();

    expect(buttonWithText(wrapper, '发货')).toBeUndefined();
    expect(buttonWithText(wrapper, '标记签收')).toBeUndefined();
  });

  it('「模拟支付成功」仅管理员可见且走回调接口', async () => {
    mockedList.mockResolvedValue(page([order({ status: 'created', paid_at: null })]));

    const merchantWrapper = await mountOrders('merchant');
    expect(buttonWithText(merchantWrapper, '模拟支付成功')).toBeUndefined();

    mockedDetail.mockResolvedValue({ payment_id: 77 } as never);
    mockedCallback.mockResolvedValue(undefined as never);
    const adminWrapper = await mountOrders('admin');
    await buttonWithText(adminWrapper, '模拟支付成功')?.trigger('click');
    await flushPromises();
    expect(mockedDetail).toHaveBeenCalled();

    expect(mockedDetail).toHaveBeenCalledWith(101);
    expect(mockedCallback).toHaveBeenCalledWith(77, true, expect.stringContaining('ADMIN-MOCK-'));
  });
});

describe('订单导出（增强）', () => {
  it('点「导出 CSV」调用导出接口并提示成功', async () => {
    mockedList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 } as never);
    mockedExport.mockResolvedValue({
      blob: new Blob(['a,b']),
      rows: 1,
      truncated: false,
    } as never);
    // jsdom 没有 createObjectURL / revokeObjectURL：打桩
    Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:test'),
      revokeObjectURL: vi.fn(),
    });
    const wrapper = await mountOrders();
    await flushPromises();

    const button = wrapper.findAll('button').find((btn) => btn.text().includes('导出 CSV'));
    await button?.trigger('click');
    await flushPromises();

    expect(mockedExport).toHaveBeenCalled();
    expect(mockedMessage.success).toHaveBeenCalledWith('已导出订单 CSV');
  });

  it('超过 5 万行被截断时明确提示（不谎称完整导出）', async () => {
    mockedList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 } as never);
    mockedExport.mockResolvedValue({
      blob: new Blob(['a,b']),
      rows: 50000,
      truncated: true,
    } as never);
    Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:test'),
      revokeObjectURL: vi.fn(),
    });
    const wrapper = await mountOrders();
    await flushPromises();

    const button = wrapper.findAll('button').find((btn) => btn.text().includes('导出 CSV'));
    await button?.trigger('click');
    await flushPromises();

    expect(mockedMessage.warning).toHaveBeenCalledWith(expect.stringContaining('5 万行上限'));
    expect(mockedMessage.success).not.toHaveBeenCalled();
  });
});

describe('异常支付退款（管理员）', () => {
  it('待退款订单显示标签，管理员可打开对话框并登记退款', async () => {
    mockedList.mockResolvedValue(
      page([
        order({
          id: 102,
          status: 'cancelled',
          payment_refund_status: 'pending',
          payment_id: 55,
        }),
      ]),
    );
    mockedRefund.mockResolvedValue({} as never);
    const wrapper = await mountOrders('admin');

    expect(wrapper.text()).toContain('待退款');
    const button = buttonWithText(wrapper, '登记退款');
    expect(button).toBeTruthy();
    await button?.trigger('click');
    await flushPromises();

    const vm = wrapper.vm as unknown as {
      refundDialog: boolean;
      refundTarget: { id: number; payment_id: number } | null;
      refundNote: string;
      submitRefund: () => Promise<void>;
    };
    expect(vm.refundDialog).toBe(true);
    expect(vm.refundTarget?.payment_id).toBe(55);
    vm.refundNote = '渠道凭证 TX-1';
    await vm.submitRefund();
    await flushPromises();

    expect(mockedRefund).toHaveBeenCalledWith(55, '渠道凭证 TX-1');
    expect(mockedMessage.success).toHaveBeenCalledWith('已登记退款，买卖双方会收到通知');
    expect(vm.refundDialog).toBe(false);
  });

  it('商户看不到「登记退款」操作（仅管理员）', async () => {
    mockedList.mockResolvedValue(
      page([
        order({
          id: 103,
          status: 'cancelled',
          payment_refund_status: 'pending',
          payment_id: 56,
        }),
      ]),
    );
    const wrapper = await mountOrders('merchant');
    expect(wrapper.text()).toContain('待退款');
    expect(buttonWithText(wrapper, '登记退款')).toBeUndefined();
  });
});

describe('通知跳转定位', () => {
  it('?focus=<id> 时把目标订单补进列表并提示', async () => {
    routeState.query = { focus: '999' };
    mockedList.mockResolvedValue(page([]));
    mockedDetail.mockResolvedValue(order({ id: 999 }) as never);
    const wrapper = await mountOrders();

    expect(mockedDetail).toHaveBeenCalledWith(999);
    expect(wrapper.text()).toContain('已定位订单 #999');
    expect(wrapper.text()).toContain('订单 #999');
  });
});
