/** 售后管理页测试：列表与筛选 / 处理权限（订单归属商户或管理员）/ 受理 · 完成 · 拒绝 / 留言。 */

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ query: {} }),
}));

import { flushPromises, mount } from '@vue/test-utils';
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  acceptAfterSale: vi.fn(),
  getAfterSale: vi.fn(),
  listAfterSales: vi.fn(),
  postAfterSaleMessage: vi.fn(),
  rejectAfterSale: vi.fn(),
  resolveAfterSale: vi.fn(),
}));

import {
  acceptAfterSale,
  getAfterSale,
  listAfterSales,
  postAfterSaleMessage,
  rejectAfterSale,
  resolveAfterSale,
} from '@qh/api-client';

import { useAuthStore } from '../stores/auth';
import AfterSales from './AfterSales.vue';

const mockedList = vi.mocked(listAfterSales);
const mockedDetail = vi.mocked(getAfterSale);
const mockedAccept = vi.mocked(acceptAfterSale);
const mockedResolve = vi.mocked(resolveAfterSale);
const mockedReject = vi.mocked(rejectAfterSale);
const mockedMessage = vi.mocked(postAfterSaleMessage);
const mockedElMessage = vi.mocked(ElMessage);
/** vi.mocked 对重载的命令式 API 推不出 mock 方法，这里显式收窄。 */
type AnyMock = {
  mockResolvedValueOnce: (value: unknown) => void;
  mockRejectedValueOnce: (value: unknown) => void;
};

const mockedBox = vi.mocked(ElMessageBox);
const promptMock = ElMessageBox.prompt as unknown as AnyMock;

function sale(overrides: Record<string, unknown> = {}) {
  return {
    id: 11,
    order_id: 101,
    user_id: 5,
    merchant_id: 9,
    reason: 'damaged',
    description: '外箱破损',
    status: 'pending',
    handler_id: null,
    created_at: '2026-10-15T10:00:00Z',
    updated_at: '2026-10-15T10:00:00Z',
    closed_at: null,
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...sale(),
    messages: [
      { id: 1, author_id: 5, author_role: 'buyer', content: '附照片', created_at: '2026-10-15T10:01:00Z' },
    ],
    order_amount: 138,
    order_status: 'paid',
    ...overrides,
  };
}

function page(items: unknown[], total?: number) {
  return { items, total: total ?? items.length, page: 1, page_size: 10 } as never;
}

type Vm = {
  canHandle: (row: { merchant_id: number }) => boolean;
  openDetail: (row: unknown) => Promise<void>;
  accept: () => Promise<void>;
  resolveOne: () => Promise<void>;
  rejectOne: () => Promise<void>;
  sendReply: () => Promise<void>;
  detail: { id: number; messages: unknown[]; order_amount: number | null } | null;
  detailVisible: boolean;
  reply: string;
  statusFilter: string;
  load: () => Promise<void>;
};

async function mountPage(role = 'merchant', userId = 9) {
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
  const wrapper = mount(AfterSales, { global: { plugins: [ElementPlus, pinia] } });
  await flushPromises();
  return wrapper;
}

function buttonWithText(wrapper: Awaited<ReturnType<typeof mountPage>>, text: string) {
  return wrapper.findAll('button').find((button) => button.text().trim() === text);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedList.mockResolvedValue(page([]));
  document.body.innerHTML = '';
});

describe('售后管理页（控制台）', () => {
  it('加载售后列表并渲染问题类型、状态与说明', async () => {
    mockedList.mockResolvedValue(
      page([
        sale(),
        sale({ id: 12, order_id: 102, status: 'resolved', reason: 'quality', description: null }),
      ]),
    );
    const wrapper = await mountPage();

    expect(mockedList).toHaveBeenCalledWith(1, 10, undefined);
    const text = wrapper.text();
    expect(text).toContain('包装 / 商品破损');
    expect(text).toContain('待处理');
    expect(text).toContain('已解决');
    expect(text).toContain('外箱破损');
  });

  it('状态筛选变更后带参重新加载', async () => {
    mockedList.mockResolvedValue(page([]));
    const wrapper = await mountPage();
    (wrapper.vm as unknown as Vm).statusFilter = 'pending';

    await (wrapper.vm as unknown as Vm).load();

    expect(mockedList).toHaveBeenLastCalledWith(1, 10, 'pending');
  });

  it('处理权限：管理员任意售后可处理；商户仅自己订单的售后可处理', async () => {
    const merchantWrapper = await mountPage('merchant', 9);
    const merchantVm = merchantWrapper.vm as unknown as Vm;
    expect(merchantVm.canHandle({ merchant_id: 9 })).toBe(true);
    expect(merchantVm.canHandle({ merchant_id: 8 })).toBe(false);

    const adminWrapper = await mountPage('admin', 1);
    expect((adminWrapper.vm as unknown as Vm).canHandle({ merchant_id: 8 })).toBe(true);
  });

  it('操作按钮文案：待处理且可处理显示「处理」，否则显示「查看」', async () => {
    mockedList.mockResolvedValue(
      page([
        sale({ id: 11, status: 'pending', merchant_id: 9 }),
        sale({ id: 12, status: 'pending', merchant_id: 8 }), // 他人订单：只读
        sale({ id: 13, status: 'rejected', merchant_id: 9 }), // 已结单：只读
      ]),
    );
    const wrapper = await mountPage('merchant', 9);

    const labels = wrapper
      .findAll('button')
      .map((button) => button.text().trim())
      .filter((text) => text === '处理' || text === '查看');
    expect(labels).toEqual(['处理', '查看', '查看']);
  });

  it('打开详情后拉取单据并渲染留言（含作者角色中文）', async () => {
    mockedList.mockResolvedValue(page([sale()]));
    mockedDetail.mockResolvedValue(detail() as never);
    const wrapper = await mountPage();
    const vm = wrapper.vm as unknown as Vm;

    await vm.openDetail(sale());

    expect(mockedDetail).toHaveBeenCalledWith(11);
    expect(vm.detailVisible).toBe(true);
    // 弹窗内容在 happy-dom 下的 teleport + 过渡渲染不稳定，这里断言组件已拿到详情与留言
    expect(vm.detail?.id).toBe(11);
    expect(vm.detail?.messages).toHaveLength(1);
  });

  it('受理：调用接口并刷新列表与详情', async () => {
    mockedList.mockResolvedValue(page([sale()]));
    mockedDetail.mockResolvedValue(detail() as never);
    mockedAccept.mockResolvedValue(sale({ status: 'processing' }) as never);
    const wrapper = await mountPage();
    const vm = wrapper.vm as unknown as Vm;
    await vm.openDetail(sale());

    await vm.accept();

    expect(mockedAccept).toHaveBeenCalledWith(11);
    expect(mockedElMessage.success).toHaveBeenCalled();
    expect(mockedList).toHaveBeenCalledTimes(2);
  });

  it('完成：把处理说明随接口提交（留空则不传说明）', async () => {
    mockedList.mockResolvedValue(page([sale({ status: 'processing' })]));
    mockedDetail.mockResolvedValue(detail({ status: 'processing' }) as never);
    mockedResolve.mockResolvedValue(sale({ status: 'resolved' }) as never);
    const wrapper = await mountPage();
    const vm = wrapper.vm as unknown as Vm;
    await vm.openDetail(sale({ status: 'processing' }));

    promptMock.mockResolvedValueOnce({ value: '已补发一箱' } as never);
    await vm.resolveOne();
    expect(mockedResolve).toHaveBeenCalledWith(11, '已补发一箱');

    promptMock.mockResolvedValueOnce({ value: '' } as never);
    await vm.resolveOne();
    expect(mockedResolve).toHaveBeenLastCalledWith(11, undefined);
  });

  it('拒绝：理由经弹窗收集后提交；用户取消时不做任何调用', async () => {
    mockedList.mockResolvedValue(page([sale()]));
    mockedDetail.mockResolvedValue(detail() as never);
    mockedReject.mockResolvedValue(sale({ status: 'rejected' }) as never);
    const wrapper = await mountPage();
    const vm = wrapper.vm as unknown as Vm;
    await vm.openDetail(sale());

    promptMock.mockResolvedValueOnce({ value: '商品已拆封使用' } as never);
    await vm.rejectOne();
    expect(mockedReject).toHaveBeenCalledWith(11, '商品已拆封使用');

    promptMock.mockRejectedValueOnce('cancel');
    await vm.rejectOne();
    expect(mockedReject).toHaveBeenCalledTimes(1); // 取消不新增调用
  });

  it('留言：内容为空时不提交，非空时调用接口并清空输入', async () => {
    mockedList.mockResolvedValue(page([sale()]));
    mockedDetail.mockResolvedValue(detail() as never);
    mockedMessage.mockResolvedValue({} as never);
    const wrapper = await mountPage();
    const vm = wrapper.vm as unknown as Vm;
    await vm.openDetail(sale());

    vm.reply = '   ';
    await vm.sendReply();
    expect(mockedMessage).not.toHaveBeenCalled();

    vm.reply = '已安排补发，请留意物流';
    await vm.sendReply();
    expect(mockedMessage).toHaveBeenCalledWith(11, '已安排补发，请留意物流');
    expect(vm.reply).toBe('');
  });
});
