/** 路线管理页测试：列表与景点选项加载 / 新建与编辑对话框 / 停靠点增删 / 删除确认。 */

import { flushPromises, mount } from '@vue/test-utils';
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  createRoute: vi.fn(),
  deleteRoute: vi.fn(),
  getRouteDetail: vi.fn(),
  listAttractions: vi.fn(),
  listRoutes: vi.fn(),
  updateRoute: vi.fn(),
}));

import {
  createRoute,
  deleteRoute,
  getRouteDetail,
  listAttractions,
  listRoutes,
} from '@qh/api-client';

import { useAuthStore } from '../stores/auth';
import RoutesManage from './RoutesManage.vue';

const mockedRoutes = vi.mocked(listRoutes);
const mockedAttractions = vi.mocked(listAttractions);
const mockedDetail = vi.mocked(getRouteDetail);
const mockedCreate = vi.mocked(createRoute);
const mockedDelete = vi.mocked(deleteRoute);
const mockedElMessage = vi.mocked(ElMessage);
const mockedBox = vi.mocked(ElMessageBox);

function route(overrides: Record<string, unknown> = {}) {
  return {
    id: 41,
    name: '青海湖环线两日',
    theme: '湖泊',
    days: 2,
    budget: 880,
    description: '经典环湖',
    created_at: '2026-10-01T00:00:00Z',
    ...overrides,
  };
}

function routeDetail(overrides: Record<string, unknown> = {}) {
  return {
    ...route(),
    stops: [{ id: 1, attraction_id: 7, attraction_name: '青海湖', day: 1, position: 1, note: '' }],
    ...overrides,
  };
}

async function mountRoutes() {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().user = {
    id: 1,
    phone: '13900000001',
    role: 'admin',
    status: 'active',
    nickname: '平台运营',
    license_no: null,
    created_at: '2026-01-01T00:00:00Z',
  } as never;
  const wrapper = mount(RoutesManage, { global: { plugins: [ElementPlus, pinia] } });
  await flushPromises();
  return wrapper;
}

type Vm = {
  load: () => Promise<void>;
  openCreate: () => void;
  openEdit: (row: unknown) => Promise<void>;
  removeRoute: (row: unknown) => Promise<void>;
  addStop: () => void;
  removeStop: (index: number) => void;
  submit: () => Promise<void>;
  dialogVisible: boolean;
  editingId: number | null;
  error: string;
  form: {
    name: string;
    theme: string;
    days: number;
    budget: number | null;
    description: string;
    stops: { attraction_id: number | null; day: number; note: string }[];
  };
};

beforeEach(() => {
  vi.clearAllMocks();
  mockedRoutes.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 } as never);
  mockedAttractions.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 } as never);
  document.body.innerHTML = '';
});

describe('路线管理页（控制台）', () => {
  it('加载路线与景点选项并渲染行', async () => {
    mockedRoutes.mockResolvedValue({ items: [route()], total: 1, page: 1, page_size: 10 } as never);
    mockedAttractions.mockResolvedValue({
      items: [
        { id: 7, name: '青海湖', city: '海南州' },
        { id: 8, name: '塔尔寺', city: '西宁市' },
      ],
      total: 2,
      page: 1,
      page_size: 50,
    } as never);

    const wrapper = await mountRoutes();

    expect(mockedRoutes).toHaveBeenCalledWith({ page: 1, page_size: 10 });
    expect(mockedAttractions).toHaveBeenCalledWith({ page_size: 50 });
    const text = wrapper.text();
    expect(text).toContain('青海湖环线两日');
    expect(text).toContain('湖泊');
  });

  it('加载失败时展示错误信息', async () => {
    mockedRoutes.mockRejectedValue(new Error('服务不可用'));
    const wrapper = await mountRoutes();

    expect((wrapper.vm as unknown as Vm).error).toBe('服务不可用');
  });

  it('新建路线：清空表单并打开对话框', async () => {
    const wrapper = await mountRoutes();
    const vm = wrapper.vm as unknown as Vm;
    vm.form.name = '残留草稿';

    vm.openCreate();

    expect(vm.dialogVisible).toBe(true);
    expect(vm.editingId).toBeNull();
    expect(vm.form.name).toBe('');
    expect(vm.form.stops).toHaveLength(1); // 默认给一个空停靠点
  });

  it('编辑路线：拉取详情回填表单（含停靠点）', async () => {
    mockedDetail.mockResolvedValue(routeDetail() as never);
    const wrapper = await mountRoutes();
    const vm = wrapper.vm as unknown as Vm;

    await vm.openEdit(route());

    expect(mockedDetail).toHaveBeenCalledWith(41);
    expect(vm.editingId).toBe(41);
    expect(vm.form.name).toBe('青海湖环线两日');
    expect(vm.form.stops).toHaveLength(1);
    expect(vm.form.stops[0].attraction_id).toBe(7);
  });

  it('停靠点可增删', async () => {
    const wrapper = await mountRoutes();
    const vm = wrapper.vm as unknown as Vm;
    vm.openCreate();
    const initial = vm.form.stops.length;

    vm.addStop();
    expect(vm.form.stops).toHaveLength(initial + 1);

    vm.removeStop(initial);
    expect(vm.form.stops).toHaveLength(initial);
  });

  it('提交新建：调用接口并关闭对话框 + 提示', async () => {
    mockedCreate.mockResolvedValue(routeDetail() as never);
    const wrapper = await mountRoutes();
    const vm = wrapper.vm as unknown as Vm;
    vm.openCreate();
    vm.form.name = '新路线';
    vm.form.theme = '草原';
    vm.form.stops[0].attraction_id = 7; // 每个停靠点必须选景点

    await vm.submit();
    await flushPromises();

    expect(mockedCreate).toHaveBeenCalledWith(
      expect.objectContaining({ name: '新路线', theme: '草原' }),
    );
    expect(mockedElMessage.success).toHaveBeenCalled();
    expect(vm.dialogVisible).toBe(false);
  });

  it('提交校验：停靠点未选景点时提示且不提交', async () => {
    const wrapper = await mountRoutes();
    const vm = wrapper.vm as unknown as Vm;
    vm.openCreate();
    vm.form.name = '缺停靠点路线';

    await vm.submit();

    expect(mockedElMessage.warning).toHaveBeenCalled();
    expect(mockedCreate).not.toHaveBeenCalled();
    expect(vm.dialogVisible).toBe(true);
  });

  it('删除路线：确认后调用接口并刷新', async () => {
    mockedRoutes.mockResolvedValue({ items: [route()], total: 1, page: 1, page_size: 10 } as never);
    mockedDelete.mockResolvedValue(null as never);
    const wrapper = await mountRoutes();

    await (wrapper.vm as unknown as Vm).removeRoute(route());
    await flushPromises();

    expect(mockedBox.confirm).toHaveBeenCalled();
    expect(mockedDelete).toHaveBeenCalledWith(41);
    expect(mockedRoutes).toHaveBeenCalledTimes(2);
  });
});
