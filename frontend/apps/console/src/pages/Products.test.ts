/** 商品管理页测试：列表与状态筛选 / 上下架 / 编辑入口仅对本人商品 / 加载失败提示。 */

import { flushPromises, mount } from '@vue/test-utils';
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  createProduct: vi.fn(),
  listMyProducts: vi.fn(),
  setProductStatus: vi.fn(),
  updateProduct: vi.fn(),
  uploadFile: vi.fn(),
}));

import { listMyProducts, setProductStatus, uploadFile } from '@qh/api-client';

import { useAuthStore } from '../stores/auth';
import Products from './Products.vue';

const mockedList = vi.mocked(listMyProducts);
const mockedStatus = vi.mocked(setProductStatus);
const mockedUpload = vi.mocked(uploadFile);
const mockedElMessage = vi.mocked(ElMessage);
const mockedBox = vi.mocked(ElMessageBox);

function product(overrides: Record<string, unknown> = {}) {
  return {
    id: 31,
    merchant_id: 9,
    name: '祁连山牦牛肉干',
    description: '风干工艺',
    price: 138,
    stock: 12,
    status: 'on_sale',
    image_url: null,
    created_at: '2026-10-01T00:00:00Z',
    ...overrides,
  };
}

function page(items: unknown[], total?: number) {
  return { items, total: total ?? items.length, page: 1, page_size: 10 } as never;
}

type Vm = {
  load: () => Promise<void>;
  statusFilter: string;
  myId: number;
  error: string;
  rows: unknown[];
};

async function mountProducts(role = 'merchant', userId = 9) {
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
  const wrapper = mount(Products, { global: { plugins: [ElementPlus, pinia] } });
  await flushPromises();
  return wrapper;
}

function buttonWithText(wrapper: Awaited<ReturnType<typeof mountProducts>>, text: string) {
  return wrapper.findAll('button').find((button) => button.text().trim() === text);
}



describe('商品主图（图片增强）', () => {
  it('列表用缩略图地址渲染主图（无缩略图字段时回退原图）', async () => {
    mockedList.mockResolvedValue(
      page([
        product({ image_url: '/api/v1/files/17', image_thumbnail_url: '/api/v1/files/17?variant=thumb' }),
        product({ id: 32, image_url: '/api/v1/files/18' }),
      ]),
    );
    const wrapper = await mountProducts();

    const srcs = wrapper.findAll('img.el-image__inner').map((img) => img.attributes('src'));
    expect(srcs).toEqual(['/api/v1/files/17?variant=thumb', '/api/v1/files/18']);
  });

  it('上传大图：服务端压缩后提示「原始 → 存入」（省 X%）', async () => {
    const wrapper = await mountProducts();
    mockedUpload.mockResolvedValue({
      id: 26,
      filename: 'big_photo.jpg',
      content_type: 'image/jpeg',
      size: 501_193,
      original_size: 6_967_288,
      is_public: true,
      url: '/api/v1/files/26',
      thumbnail_url: '/api/v1/files/26?variant=thumb',
    } as never);

    buttonWithText(wrapper, '上架商品')?.trigger('click');
    await flushPromises();

    // 弹窗里的文件输入（el-upload）→ 模拟选中本地大图
    const input = wrapper.find<HTMLInputElement>('input[type="file"]');
    expect(input.exists()).toBe(true);
    const file = new File([new Uint8Array([1, 2, 3])], 'big_photo.jpg', { type: 'image/jpeg' });
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true });
    await input.trigger('change');
    await flushPromises();

    expect(mockedUpload).toHaveBeenCalledWith(file, { public: true });
    expect(mockedElMessage.success).toHaveBeenCalledWith(
      expect.stringContaining('6.6 MB → 489 KB'),
    );
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  mockedList.mockResolvedValue(page([]));
  document.body.innerHTML = '';
});

describe('商品管理页（控制台）', () => {
  it('加载商品列表并渲染名称、价格与状态', async () => {
    mockedList.mockResolvedValue(
      page([product(), product({ id: 32, status: 'off_shelf', name: '下架商品' })]),
    );
    const wrapper = await mountProducts();

    expect(mockedList).toHaveBeenCalledWith(1, 10, undefined);
    const text = wrapper.text();
    expect(text).toContain('祁连山牦牛肉干');
    expect(text).toContain('138');
    expect(text).toContain('在售');
    expect(text).toContain('已下架');
  });

  it('状态筛选变更后带参重新加载', async () => {
    const wrapper = await mountProducts();
    const vm = wrapper.vm as unknown as Vm;
    vm.statusFilter = 'off_shelf';

    await vm.load();

    expect(mockedList).toHaveBeenLastCalledWith(1, 10, 'off_shelf');
  });

  it('加载失败时展示错误信息', async () => {
    mockedList.mockRejectedValue(new Error('商户无权访问'));
    const wrapper = await mountProducts();

    expect((wrapper.vm as unknown as Vm).error).toBe('商户无权访问');
  });

  it('下架：确认后调用状态接口并刷新列表', async () => {
    mockedList.mockResolvedValue(page([product()]));
    mockedStatus.mockResolvedValue(product({ status: 'off_shelf' }) as never);
    const wrapper = await mountProducts();

    const button = buttonWithText(wrapper, '下架');
    expect(button).toBeTruthy();
    await button?.trigger('click');
    await flushPromises();

    expect(mockedBox.confirm).toHaveBeenCalled();
    expect(mockedStatus).toHaveBeenCalledWith(31, 'off_shelf');
    expect(mockedElMessage.success).toHaveBeenCalled();
    expect(mockedList).toHaveBeenCalledTimes(2);
  });

  it('上架：已下架商品显示「上架」并调用状态接口', async () => {
    mockedList.mockResolvedValue(page([product({ status: 'off_shelf' })]));
    mockedStatus.mockResolvedValue(product({ status: 'on_sale' }) as never);
    const wrapper = await mountProducts();

    await buttonWithText(wrapper, '上架')?.trigger('click');
    await flushPromises();

    expect(mockedStatus).toHaveBeenCalledWith(31, 'on_sale');
  });

  it('编辑入口仅对本人商品显示（管理员看不到他人商品的编辑按钮）', async () => {
    mockedList.mockResolvedValue(page([product({ id: 33, merchant_id: 77, name: '他人商品' })]));
    const wrapper = await mountProducts('admin', 1);

    expect(buttonWithText(wrapper, '编辑')).toBeUndefined();
  });

  it('本人商品显示编辑按钮', async () => {
    mockedList.mockResolvedValue(page([product()]));
    const wrapper = await mountProducts('merchant', 9);

    expect(buttonWithText(wrapper, '编辑')).toBeTruthy();
  });
});
